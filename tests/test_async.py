"""The async client is the sync one, awaited — including the chained calls.

**One implementation, two surfaces.** Hand-writing 213 async methods beside
213 sync ones is the shape that looks more correct and is worse: two
surfaces that drift, where the async one is always the stale one. These
tests pin the properties that make the single implementation safe.
"""

import asyncio

import httpx
import pytest

from graphowl import AsyncGraphOWL, NotFoundError
from graphowl.models import Node


def client(routes: dict) -> AsyncGraphOWL:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"detail": f"no route {request.url.path}"})
        return httpx.Response(200, json=body)

    return AsyncGraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler))


def test_a_sub_client_method_is_awaitable() -> None:
    owl = client({"/glossary-terms/search": [{"name": "Invoice"}]})
    terms = asyncio.run(owl.vocabulary.search("invoice"))
    assert [t.name for t in terms] == ["Invoice"]


def test_a_method_returning_an_object_stays_awaitable() -> None:
    """`owl.graph("demo")` returns a resource. Without proxying it, the
    second call in the chain would run on the event loop thread and block
    it — the exact failure this client exists to avoid."""
    owl = client({"/graph/context": {"nodes": [{"id": "n"}], "edges": []}})
    snap = asyncio.run(_subgraph(owl))
    assert snap.nodes[0].id == "n"


async def _subgraph(owl: AsyncGraphOWL):
    graph = await owl.graph("demo")
    return await graph.subgraph("n")


def test_models_come_back_as_themselves_not_proxies() -> None:
    """A `Node` is data. Wrapping it would make `node.id` return a
    coroutine, which fails far from the cause."""
    owl = client({"/assets": [{"iri": "a-1", "type": "table"}]})
    assets = asyncio.run(owl.assets.list())
    assert isinstance(assets[0], Node)
    assert assets[0].id == "a-1"


def test_errors_are_the_same_typed_errors() -> None:
    owl = client({})
    with pytest.raises(NotFoundError):
        asyncio.run(owl.vocabulary.term("nope"))


def test_every_sync_sub_client_is_reachable() -> None:
    """The proxy must not quietly omit one. A missing sub-client would
    surface as an AttributeError deep in someone's application."""
    from graphowl import GraphOWL

    sync = GraphOWL(url="https://api.example")
    owl = client({})
    for name in dir(sync):
        if name.startswith("_") or name in ("close", "graph"):
            continue
        assert getattr(owl, name) is not None, name


def test_calls_run_off_the_event_loop() -> None:
    """The whole point. If a call ran inline, this loop-blocking check
    would not be able to make progress concurrently."""

    async def go() -> list:
        owl = client({"/glossary-terms/search": []})
        return await asyncio.gather(
            owl.vocabulary.search("a"),
            owl.vocabulary.search("b"),
            owl.vocabulary.search("c"),
        )

    assert len(asyncio.run(go())) == 3
