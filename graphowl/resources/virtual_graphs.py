"""Virtual graphs — ask a source database in place, through a mapping a reviewer approved.

    owl.virtual_graphs.query("dairy", "MATCH (l:MilkLot)-[:hasFarm]->(f:Farm) RETURN l.lot_id, f.name")

Read-only and admin-only on the server. Nothing is copied: every answer is rows read from the source database
now, and says which approved version of which mapping produced it. A graph that is not approved, or whose
source no longer matches it, answers with an error — never with an empty result in its place.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..exceptions import GraphOWLError
from ._base import Resource

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _name(value: str) -> str:
    """A graph's name is letters, digits and underscores; anything else is refused here rather than
    spliced into a path, where `a/b` would address a different route."""
    if not _NAME.match(value):
        raise GraphOWLError(f"`{value}` is not a virtual graph name: use letters, digits and underscores")
    return value


class VirtualGraphs(Resource):
    def list(self) -> list[dict[str, Any]]:
        """The newest version of each graph in the workspace."""
        return (self._get("/virtual-graphs") or {}).get("graphs", [])

    def versions(self, name: str) -> list[dict[str, Any]]:
        """Every version of one graph, newest first."""
        return (self._get(f"/virtual-graphs/{_name(name)}") or {}).get("versions", [])

    def save(self, name: str, mapping: dict[str, Any]) -> dict[str, Any]:
        """Save the draft mapping (`nodes`, `edges`, `limits`, ...); a proposed version is never changed."""
        return self._put(f"/virtual-graphs/{_name(name)}", {"mapping": mapping})

    def validate(self, name: str) -> list[dict[str, Any]]:
        """What stops the mapping being approved; empty means nothing does."""
        return (self._post(f"/virtual-graphs/{_name(name)}/validate", {}) or {}).get("findings", [])

    def propose(self, name: str) -> dict[str, Any]:
        return self._post(f"/virtual-graphs/{_name(name)}/propose", {})

    def grants(self, name: str) -> dict[str, Any]:
        """What the role the source is reached as may change among the mapped tables."""
        return self._get(f"/virtual-graphs/{_name(name)}/grants")

    def decide(
        self,
        name: str,
        version: int,
        outcome: str,
        words: str,
        *,
        acknowledge_writable: bool = False,
    ) -> dict[str, Any]:
        """Approve or reject a proposed version, in the reviewer's own words. An approval is refused while the
        source role can write, unless `acknowledge_writable` says the reviewer knows."""
        if outcome not in ("approved", "rejected"):
            raise GraphOWLError("`outcome` is `approved` or `rejected`")
        body: dict[str, Any] = {"version": version, "outcome": outcome, "words": words}
        if acknowledge_writable:
            body["acknowledgeWritable"] = True
        return self._post(f"/virtual-graphs/{_name(name)}/decide", body)

    def revalidate(self, name: str) -> str:
        """Compare the approved version with the source as it is now; returns `fresh`, `nowStale`, ..."""
        return (self._post(f"/virtual-graphs/{_name(name)}/revalidate", {}) or {}).get("drift", "")

    def query(
        self,
        name: str,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Ask the source. Values go in `params` as `$name`, never into the text. Returns the whole answer:
        `columns`, `rows`, `truncated`, `timings`, `plan`, `sql` and which mapping version answered."""
        body: dict[str, Any] = {"query": query, "params": params or {}}
        if language is not None:
            body["language"] = language
        return self._post(f"/virtual-graphs/{_name(name)}/query", body)

    def rows(self, name: str, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """`query`, with each row as a dict keyed by column — what a notebook wants. A `truncated` answer
        raises rather than silently handing back part of the result."""
        answer = self.query(name, query, params)
        if answer.get("truncated"):
            raise GraphOWLError("the answer was cut at the graph's row limit; narrow the query")
        columns = answer.get("columns", [])
        return [dict(zip(columns, row, strict=False)) for row in answer.get("rows", [])]

    def similar(self, name: str, class_: str, property_: str, key: list[Any], top_k: int) -> dict[str, Any]:
        """Nearest neighbours by a mapped embedding column, as typed ids ready to be `$ids`."""
        return self._post(
            f"/virtual-graphs/{_name(name)}/similar",
            {"class": class_, "property": property_, "key": key, "topK": top_k},
        )

    def log(self, name: str) -> list[dict[str, Any]]:
        """The audit trail: hashes and counts, never rows or parameters."""
        return (self._get(f"/virtual-graphs/{_name(name)}/log") or {}).get("entries", [])

    def source_schema(self, source: str) -> dict[str, Any]:
        """The tables of a scanned source, as the mapping screen draws them."""
        return self._get(f"/virtual-sources/{quote(source, safe='')}/schema")

    def parse_ddl(self, source: str, ddl: str) -> dict[str, Any]:
        """A `CREATE PROPERTY GRAPH` statement as a draft mapping, checked against the scan."""
        return self._post(f"/virtual-sources/{quote(source, safe='')}/parse-ddl", {"ddl": ddl})
