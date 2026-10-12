"""The catalogued things themselves — and everything hung off them.

**Named as its own primitive rather than folded into `graph`.** An asset is
the noun this system is about: it has owners, followers, versions, threads,
announcements, memories and proposals. Reaching those through
`owl.graph.assets_owners_put(...)` would hide the noun behind the store it
happens to live in, which is the exact opposite of what
this SDK is for.

`graph` remains "what connects to what". This is "what exists, and what is
true about it".
"""

from __future__ import annotations

from typing import Any

from ..models import Node
from ._base import Resource, rows
from .graph import _node, _snapshot


class Assets(Resource):
    # ---- finding them -------------------------------------------------

    def list(self, *, limit: int | None = None, offset: int | None = None, **filters: Any) -> list[Node]:
        return [_node(r) for r in rows(self._get("/assets", limit=limit, offset=offset, **filters))]

    def get(self, asset_id: str) -> Node:
        return _node(self._get(f"/assets/{asset_id}") or {})

    def search(self, query: str, **params: Any) -> list[Node]:
        return [_node(r) for r in rows(self._get("/assets/search", q=query, **params))]

    def roots(self) -> list[Node]:
        """Assets with no parent — the top of each source's tree."""
        return [_node(r) for r in rows(self._get("/assets/roots"))]

    def children(self, asset_id: str) -> list[Node]:
        return [_node(r) for r in rows(self._get(f"/assets/{asset_id}/children"))]

    def ancestors(self, asset_id: str) -> list[Node]:
        """The chain from this asset up to its root."""
        return [_node(r) for r in rows(self._get(f"/assets/{asset_id}/ancestors"))]

    def stats(self) -> dict[str, Any]:
        return self._get("/assets/stats") or {}

    # ---- changing them ------------------------------------------------

    def create(self, **body: Any) -> Node:
        return _node(self._post("/assets", body) or {})

    def update(self, asset_id: str, **changes: Any) -> Node:
        """Partial update. Only the fields you pass are touched.

        Identity fields are absent from the request shape by construction
        rather than rejected at runtime — there is nothing a caller can
        send that would move an asset's id or fully-qualified name.
        """
        return _node(self._patch(f"/assets/{asset_id}", changes) or {})

    def delete(self, asset_id: str) -> None:
        self._delete(f"/assets/{asset_id}")

    def restore(self, asset_id: str) -> Node:
        """Undo a delete. Soft-deleted assets keep their history, which is
        why this exists at all."""
        return _node(self._post(f"/assets/{asset_id}/restore", {}) or {})

    # ---- who is responsible -------------------------------------------

    def owners(self, asset_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/assets/{asset_id}/owners"))

    def set_owners(self, asset_id: str, owners: list[dict[str, Any]] | dict[str, Any]) -> Any:
        """Replace the owner set. A PUT, not a POST: ownership is a
        complete statement, and adding one owner without saying who else
        remains is how two systems end up disagreeing about it."""
        return self._put(f"/assets/{asset_id}/owners", owners)

    def follow(self, asset_id: str, user_id: str) -> Any:
        return self._put(f"/assets/{asset_id}/followers/{user_id}")

    def unfollow(self, asset_id: str, user_id: str) -> None:
        self._delete(f"/assets/{asset_id}/followers/{user_id}")

    # ---- what is true about them ---------------------------------------

    def graph(self, asset_id: str, **params: Any) -> Any:
        """This asset's immediate neighbourhood."""
        return _snapshot(self._get(f"/assets/{asset_id}/graph", **params))

    def versions(self, asset_id: str) -> list[dict[str, Any]]:
        """Every recorded version. The catalog is bitemporal, so this is
        history rather than an audit log bolted on beside it."""
        return rows(self._get(f"/assets/{asset_id}/versions"))

    def activity(self, asset_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/assets/{asset_id}/activity"))

    def memories(self, asset_id: str) -> list[dict[str, Any]]:
        """What agents and people have recorded about this asset."""
        return rows(self._get(f"/assets/{asset_id}/memories"))

    def contradictions(self, asset_id: str) -> list[dict[str, Any]]:
        """Sources asserting incompatible things about this asset."""
        return rows(self._get(f"/assets/{asset_id}/contradictions"))

    def analytics(self, asset_id: str, **params: Any) -> dict[str, Any]:
        """Structural measures for this asset — centrality and the like.

        Addressed by asset UUID. `owl.graph().analytics(seed=...)` answers
        the same kind of question for **any** subject, including ones that
        have no asset row; both are bounded, and neither computes over the
        entire graph.
        """
        return self._get(f"/assets/{asset_id}/analytics", **params) or {}

    def resolve(self, asset_id: str, **body: Any) -> dict[str, Any]:
        """Resolve this asset against a candidate identity."""
        return self._post(f"/assets/{asset_id}/resolve", body) or {}

    # ---- lifecycle and organisation ------------------------------------
    #
    # Where an asset sits organisationally, what replaced it, and how its
    # schema has moved. Distinct from `update()`: these are transitions with
    # their own semantics, not fields.

    def set_lifecycle(self, asset_id: str, **body: Any) -> Node:
        """Move an asset through its lifecycle — draft, live, deprecated.

        A transition, not a status field, because *when* something was
        deprecated and by whom is the part a consumer downstream needs.
        """
        return _node(self._post(f"/assets/{asset_id}/lifecycle", body) or {})

    def domain(self, asset_id: str) -> dict[str, Any]:
        """Which business domain owns this asset."""
        return self._get(f"/assets/{asset_id}/domain") or {}

    def set_domain(self, asset_id: str, **body: Any) -> Node:
        return _node(self._post(f"/assets/{asset_id}/domain", body) or {})

    def clear_domain(self, asset_id: str) -> Node:
        """Answers 200 with the updated asset, not 204."""
        return _node(self._delete(f"/assets/{asset_id}/domain") or {})

    def data_products(self, asset_id: str) -> list[dict[str, Any]]:
        """Which published products include this asset."""
        return rows(self._get(f"/assets/{asset_id}/data-products"))

    def successor(self, fqn: str) -> dict[str, Any]:
        """What replaced a deprecated asset.

        Addressed by fully-qualified name rather than id: a consumer that
        finds a dead asset usually has the name from a query, not the
        catalogue's internal identifier.
        """
        return self._get(f"/assets/{fqn}/successor") or {}

    def record_schema_change(self, fqn: str, **body: Any) -> dict[str, Any]:
        """Report that a source's schema moved.

        The input to drift detection: a change reported here is compared
        against the mapping that was built on the old shape.
        """
        return self._post(f"/assets/{fqn}/schema-change", body) or {}

    def lpg_node(self, asset_id: str) -> dict[str, Any]:
        """This asset as a property-graph node — its own facts, flattened.

        The label-property-graph view, for consumers that speak that model
        rather than RDF. A projection, not a second source of truth.
        """
        return self._get(f"/assets/{asset_id}/lpg-node") or {}

    # ---- talking about them --------------------------------------------

    def threads(self, asset_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/assets/{asset_id}/threads"))

    def open_thread(self, asset_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/assets/{asset_id}/threads", body) or {}

    def announcements(self, asset_id: str) -> list[dict[str, Any]]:
        """Every announcement ever made about this asset."""
        return rows(self._get(f"/assets/{asset_id}/announcements"))

    def active_announcements(self, asset_id: str) -> list[dict[str, Any]]:
        """Only the ones still in force.

        A separate method rather than a flag: "is there a deprecation
        notice on this right now" is the question people actually ask, and
        burying it behind `active_only=True` makes the default answer the
        less useful one.
        """
        return rows(self._get(f"/assets/{asset_id}/announcements/active"))

    def announce(self, asset_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/assets/{asset_id}/announcements", body) or {}

    def change_proposals(self, asset_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/assets/{asset_id}/change-proposals"))

    def propose_change(self, asset_id: str, **body: Any) -> dict[str, Any]:
        """Propose a change for a human to accept or reject. Never applies."""
        return self._post(f"/assets/{asset_id}/change-proposals", body) or {}
