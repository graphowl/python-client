"""Three levels of asking, and they are not interchangeable.

    owl.query.sparql(...)     raw, you wrote the query
    owl.query.cypher(...)     raw, other syntax
    owl.graph("g").query(...) graph-native
    owl.semantic.ask("...")   planned by the agent pipeline

The raw levels are exact and require you to know the vocabulary. `ask` is
none of those things: it plans, retrieves, reasons and explains, and it
returns its trace so the working can be checked. An answer whose derivation
cannot be inspected is the failure mode the pipeline was built to avoid, so
returning only the prose would defeat it.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows



class Query(Resource):
    def sparql(self, query: str) -> list[dict[str, Any]]:
        return rows(self._post("/sparql", {"query": query}))

    def search_nodes(self, q: str, **params: Any) -> dict[str, Any]:
        """Graph subjects matching a question by meaning. The whole answer,
        not just `hits`: `available: False` (no embeddings yet) and an empty
        result are different things and must not look the same."""
        return self._get("/search/nodes", q=q, **params) or {}

    def similar_nodes(self, subject: str, **params: Any) -> dict[str, Any]:
        """Subjects nearest to `subject` in embedding space, as the same
        envelope as `search_nodes`."""
        return self._get("/search/nodes/similar", subject=subject, **params) or {}

    def node_embedding(self, subject: str, **params: Any) -> dict[str, Any]:
        """Whether `subject` is embedded, and with what."""
        return self._get("/search/nodes/embedding", subject=subject, **params) or {}

    def cypher(self, query: str) -> list[dict[str, Any]]:
        return rows(self._post("/cypher", {"query": query}))


class SemanticAnswer:
    """An answer plus the working that produced it."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    @property
    def text(self) -> str:
        return self.raw.get("text") or ""

    @property
    def agents(self) -> list[str]:
        """The pipeline stages that ran, in order."""
        return list(self.raw.get("agents") or [])

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Which tools each stage called, and how often."""
        return list(self.raw.get("tools") or [])

    @property
    def failed(self) -> bool:
        return self.raw.get("status") == "error"

    @property
    def error(self) -> str | None:
        return self.raw.get("error")

    def __str__(self) -> str:
        return self.text


class Semantic(Resource):
    """Ask in words.

    Talks to the agent service rather than GraphOWL itself — a separate
    process, because the language boundary is the process boundary
    (`00j-language-boundaries.md`). It is optional: a deployment without it
    still has the other eight primitives, so the SDK reports its absence as
    a plain error rather than failing to import.
    """

    def __init__(self, transport: Any, service_url: str) -> None:
        super().__init__(transport)
        self._service = service_url.rstrip("/")

    def ask(self, question: str, *, provider: str | None = None, model: str | None = None) -> SemanticAnswer:
        """Ask, and block until the pipeline has answered.

        Returns the trace alongside the text. For a live trace as it
        happens, stream the service's own SSE endpoint — the console does
        exactly that, and duplicating its event loop here would be a
        second implementation to keep in step.
        """
        import httpx

        from ..exceptions import GraphOWLError, TransportError

        body: dict[str, Any] = {"question": question}
        if provider and model:
            body |= {"provider": provider, "model": model}
        try:
            with httpx.Client(base_url=self._service, timeout=600.0) as client:
                started = client.post("/questions", json=body)
                started.raise_for_status()
                thread_id = started.json()["threadId"]
                # The service streams; a blocking caller wants the finished
                # run, so consume the stream to completion and then read
                # the stored summary, which is the same data the console's
                # Agent runs screen shows.
                with client.stream("GET", f"/questions/{thread_id}/stream") as stream:
                    for _ in stream.iter_lines():
                        pass
                runs = client.get("/questions").json()
        except httpx.HTTPError as exc:
            raise TransportError(f"the agent service is unreachable: {exc}") from exc
        except (KeyError, ValueError) as exc:
            raise GraphOWLError(f"the agent service returned an unexpected body: {exc}") from exc

        run = next((r for r in runs if r.get("threadId") == thread_id), None)
        return SemanticAnswer(run or {})
