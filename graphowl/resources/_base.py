from __future__ import annotations

from typing import Any

from .._transport import Transport


class Resource:
    """Shared base. Holds the transport, nothing else.

    Sub-clients are deliberately thin: the value of the SDK is the *shape*
    of the surface, not machinery behind it. A resource that grows caching
    or lazy relationship loading has started becoming an ORM, which
    is ruled out by design — the graph is not local, and
    pretending otherwise is how a client starts disagreeing with the
    server.
    """

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def _get(self, path: str, **params: Any) -> Any:
        return self._t.request("GET", path, params=_clean(params) or None)

    def _post(
        self,
        path: str,
        body: Any = None,
        *,
        headers: dict[str, str] | None = None,
        idempotent: bool = False,
        **params: Any,
    ) -> Any:
        return self._t.request(
            "POST", path, json=body, params=_clean(params) or None,
            headers=headers, idempotent=idempotent,
        )

    def _put(self, path: str, body: Any = None) -> Any:
        return self._t.request("PUT", path, json=body)

    def _patch(self, path: str, body: Any = None) -> Any:
        return self._t.request("PATCH", path, json=body)

    def _delete(self, path: str, **params: Any) -> Any:
        return self._t.request("DELETE", path, params=_clean(params) or None)


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop unset parameters.

    Sending `?limit=None` is not the same as sending nothing: several
    endpoints validate their query string strictly and answer 400 rather
    than ignoring a null, so an optional argument left unset must not
    reach the wire at all.
    """
    return {k: v for k, v in params.items() if v is not None}


#: The envelopes the API pages collections in. Extended when a route
#: introduces a new one — which is a deliberate act, because the
#: alternative was silently returning nothing.
ENVELOPE_KEYS = (
    "items", "data", "results", "rows", "nodes", "assets", "terms", "packs",
    # Found by the loud path above, not by reading the spec — `owners` was
    # silently returning `[]` for every asset that had any.
    "owners",
)


def rows(payload: object) -> list[Any]:
    """A list response, whichever envelope it arrived in.

    The API pages some collections (`{"data": [...]}`, `{"items": [...]}`)
    and returns others bare. Handling both here means no caller writes
    that branch, and a collection that gains paging later does not break
    them.
    """
    if isinstance(payload, dict):
        for key in ENVELOPE_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # **Not `[]`.** An envelope nobody taught this function about and a
        # collection with nothing in it are different facts, and returning
        # the same value for both is how `paths()` reported "no route"
        # while the server was returning three: the key was `paths`, which
        # was not on the list, so a direct edge became an empty answer with
        # no error anywhere. Failing loudly here costs one exception the
        # first time a collection gains a new envelope, and saves a caller
        # from acting on a confident wrong answer.
        from ..exceptions import GraphOWLError

        raise GraphOWLError(
            f"unrecognised list envelope {sorted(payload)!r} — no key among "
            f"{', '.join(ENVELOPE_KEYS)} held a list"
        )
    return payload if isinstance(payload, list) else []
