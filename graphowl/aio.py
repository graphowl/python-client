"""The async client.

    from graphowl import AsyncGraphOWL

    owl = AsyncGraphOWL(url="http://localhost:8080", api_key="...")
    terms = await owl.vocabulary.search("invoice")

**Every method the sync client has, awaitable, with no second
implementation.** Each call runs on a worker thread via
`asyncio.to_thread`, so the event loop is never blocked and there is
exactly one place where each endpoint's path, parameters and response
shape are written down.

**The tradeoff, stated plainly.** A thread per in-flight call is fine for
what this client is for: an application backend making a handful of calls
per request, or a notebook. It is *not* the right shape for fanning out
hundreds of concurrent requests — the thread pool becomes the limit, not
the network. If that is the workload, drive several sync clients from a
process pool, or ask for a natively-async transport and it can be built
against the same resources.

The alternative — hand-writing one async method beside every sync one — is
the shape that looks more correct and is worse: two surfaces that drift,
where the async one is always the stale one.

This paragraph used to carry a count. It said 213 while the real figure was
311, because a number in prose has nothing checking it and the argument
never needed one — the point holds at any size, and holds harder the larger
the surface gets.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .client import GraphOWL


class _AsyncProxy:
    """Wraps one sub-client, awaiting each of its methods.

    Attribute access returns either a coroutine function (for a method) or
    a nested proxy (for anything that is itself an object with methods) —
    so `await owl.assets.list()` and `await owl.graph().subgraph(...)`
    both work without either being special-cased.
    """

    def __init__(self, wrapped: object) -> None:
        self._wrapped = wrapped

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._wrapped, name)
        if not callable(attr):
            return attr

        async def call(*args: Any, **kwargs: Any) -> Any:
            result = await asyncio.to_thread(attr, *args, **kwargs)
            # A method returning a live object — `owl.graph("demo")`,
            # `owl.mapping.create(...)` — must stay awaitable too, or the
            # second call in a chain would block the loop.
            if _is_resource_like(result):
                return _AsyncProxy(result)
            return result

        return call

    def __repr__(self) -> str:
        return f"<async {self._wrapped!r}>"


def _is_resource_like(value: object) -> bool:
    """Whether a returned value is a thing you call further methods on.

    Deliberately narrow: models (`Node`, `Term`, `ValidationRun`) are data
    and must come back as themselves, not wrapped in a proxy that would
    make `node.id` an accident waiting to happen.
    """
    from .resources._base import Resource

    if isinstance(value, Resource):
        return True
    module = type(value).__module__
    return module.startswith("graphowl.resources") and hasattr(value, "_r")


class AsyncGraphOWL:
    """Same surface as `GraphOWL`, every call awaitable."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._sync = GraphOWL(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._sync, name)
        if _is_resource_like(attr):
            return _AsyncProxy(attr)
        if callable(attr):
            return _AsyncProxy(self._sync).__getattr__(name)
        return attr

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)

    async def __aenter__(self) -> AsyncGraphOWL:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
