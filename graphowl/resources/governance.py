"""Whether it is allowed.

Policies, agent capabilities, and the audit trail. Kept apart from
`validation` deliberately: validation asks whether the data is *well formed*,
governance asks whether an actor may *do* something. A shape violation and a
missing capability are different problems with different fixes, and a single
"is this OK" call would blur them.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows



class Governance(Resource):
    def policies(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        return rows(self._get("/policies", limit=limit))

    def agent_grants(self) -> list[dict[str, Any]]:
        """Which agents hold which capabilities."""
        return rows(self._get("/agents/grants"))

    def get_grant(self, agent_id: str) -> dict[str, Any]:
        """One agent's current capabilities.

        The read half of `grant`/`revoke`: knowing what an agent is
        already allowed to do is the question a caller asks *before*
        deciding whether to change it, and `agent_grants()` only lists
        every grant, not one in particular.
        """
        return self._get(f"/agents/{agent_id}/grant") or {}

    def grant(self, agent_id: str, capabilities: list[str]) -> dict[str, Any]:
        """Grant or replace an agent's capabilities. Admins only, server-side.

        There is deliberately no delete, grant, policy, role or
        certification capability an agent can hold — the server rejects
        those names. An agent that could grant itself capabilities has no
        capability model at all.
        """
        return self._t.request(
            "PUT", f"/agents/{agent_id}/grant", json={"capabilities": capabilities}
        )

    def revoke(self, agent_id: str) -> None:
        self._t.request("DELETE", f"/agents/{agent_id}/grant")

    def dry_run_policy(self, **body: Any) -> dict[str, Any]:
        """What a policy *would* deny, before it denies anything.

        The direction that matters: a policy meant to exclude one path
        which in fact matches nothing enforces nothing at all, while
        looking correct. This is how you find that out.
        """
        return self._post("/policies/dry-run", body) or {}

    def delete_policy(self, name: str) -> None:
        self._delete(f"/policies/{name}")

    def create_policy(self, **body: Any) -> dict[str, Any]:
        return self._post("/policies", body) or {}

    def agent_activity(self, agent_id: str, **params: Any) -> list[dict[str, Any]]:
        """Everything an agent has done. The audit trail that makes
        granting a capability a reversible decision."""
        return rows(self._get(f"/agents/{agent_id}/activity", **params))

    # ---- people and teams ---------------------------------------------------

    def me(self) -> dict[str, Any]:
        """Who this credential is."""
        return self._get("/me") or {}

    def auth_config(self) -> dict[str, Any]:
        """How this deployment authenticates — issuer, flows.

        Read before constructing a client in an application: it is how a
        caller learns whether to expect OIDC or a bearer token.
        """
        return self._get("/auth/config") or {}

    def users(self) -> list[dict[str, Any]]:
        """Everyone this deployment knows about.

        **This comment used to say the route did not exist.** It said "the API
        offers neither" of `users()` and `create_user()`, and that was true of
        exactly one of them: `GET /users` has been routed all along, so the
        note was half a real decision and half a wrong premise nobody
        re-checked. Corrected 28 August 2026 by the contract, not by memory.

        Each row carries `isBot`, which is how a reviewer picker tells the
        seeded `system` account from a person — without it the picker offers
        an account that can never be the authenticated actor an approval
        compares against.
        """
        return rows(self._get("/users"))

    # There is still deliberately no `create_user()`. Users arrive through
    # the identity provider, and a catalogue that could mint them would be a
    # second, weaker source of truth for who exists. It was written here from
    # REST habit and reached the console's HTML with a 200.

    def update_user(self, user_id: str, **body: Any) -> dict[str, Any]:
        return self._put(f"/users/{user_id}", body) or {}

    def delete_user(self, user_id: str) -> None:
        self._delete(f"/users/{user_id}")

    def set_roles(self, user_id: str, roles: Any) -> Any:
        return self._put(f"/users/{user_id}/roles", roles)

    def user_follows(self, user_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/users/{user_id}/follows"))

    def user_change_proposals(self, user_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/users/{user_id}/change-proposals"))

    def teams(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/teams", **params))

    def create_team(self, **body: Any) -> dict[str, Any]:
        return self._post("/teams", body) or {}

    def delete_team(self, team_id: str) -> None:
        self._delete(f"/teams/{team_id}")

    def team_children(self, team_id: str) -> list[dict[str, Any]]:
        """Sub-teams. Teams nest, so ownership can be assigned at the
        level someone actually operates at."""
        return rows(self._get(f"/teams/{team_id}/children"))

    # ---- classifications, tags and labels -----------------------------------
    #
    # Three layers that get conflated and are not the same thing:
    #
    #   classification  the *scheme* — "PII", with its levels
    #   tag             one term within a scheme — "PII.Email"
    #   label           that tag applied to a specific subject
    #
    # Only the third is a claim about data. The first two are vocabulary, and
    # a system that stores them as one flat list cannot answer "which scheme
    # does this come from" — which is the question an auditor asks first.

    def classifications(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/classifications", **params))

    def create_classification(self, **body: Any) -> dict[str, Any]:
        return self._post("/classifications", body) or {}

    def delete_classification(self, classification_id: str) -> None:
        self._delete(f"/classifications/{classification_id}")

    def add_tag(self, classification_id: str, **body: Any) -> dict[str, Any]:
        """Add a tag to a classification scheme."""
        return self._post(f"/classifications/{classification_id}/tags", body) or {}

    def tags(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/tags", **params))

    def delete_tag(self, fqn: str) -> dict[str, Any]:
        """Answers 200 with what it removed, not 204 — deleting a tag
        detaches every label using it, and the count is the thing a caller
        needs to see before deciding it was a good idea."""
        return self._delete(f"/tags/{fqn}") or {}

    def tag_usage(self, fqn: str) -> dict[str, Any]:
        """How widely this tag is applied: `byKind` and a `total`.

        **A summary, not a list of the things labelled**, and it was
        declared `list[dict]` — which made it silently `[]` for a tag in
        heavy use. Returning the object is what the route offers; naming
        it a list promised an enumeration nothing here provides.
        """
        return self._get(f"/tags/{fqn}/usage") or {}

    def labels(self, target_fqn: str) -> list[dict[str, Any]]:
        """The tags applied to one subject."""
        return rows(self._get(f"/labels/{target_fqn}"))

    def label(self, target_fqn: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/labels/{target_fqn}", body) or {}

    def unlabel(self, target_fqn: str, tag_fqn: str) -> None:
        self._delete(f"/labels/{target_fqn}/{tag_fqn}")

    def confirm_label(self, target_fqn: str, tag_fqn: str, **body: Any) -> dict[str, Any]:
        """Accept a suggested label.

        Suggested, confirmed and rejected are three states, not a boolean.
        A label a machine proposed and nobody has looked at must not read
        the same as one a person stood behind — that distinction is the
        entire value of the suggestion queue.
        """
        return self._post(f"/labels/{target_fqn}/{tag_fqn}/confirm", body) or {}

    def reject_label(self, target_fqn: str, tag_fqn: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/labels/{target_fqn}/{tag_fqn}/reject", body) or {}

    def propagate_label(self, target_fqn: str, tag_fqn: str, **body: Any) -> dict[str, Any]:
        """Push a label down the lineage graph.

        The reason classification scales at all: labelling one source column
        PII and propagating beats labelling four hundred derived ones by
        hand — and, unlike the hand version, it can be re-run when lineage
        changes.
        """
        return self._post(f"/labels/{target_fqn}/{tag_fqn}/propagate", body) or {}

    def label_suggestions(self, **params: Any) -> list[dict[str, Any]]:
        """Labels proposed and not yet decided."""
        return rows(self._get("/label-suggestions", **params))

    # ---- certification -------------------------------------------------------
    #
    # A statement that somebody vouched for an asset, and when that vouching
    # expires. The expiry is the point: a certification with no recertification
    # date is an assertion about the past being read as a fact about the
    # present.

    def certification_types(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/certification-types", **params))

    def create_certification_type(self, **body: Any) -> dict[str, Any]:
        return self._post("/certification-types", body) or {}

    def certifications(self, target_fqn: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/certifications/{target_fqn}"))

    def certify(self, target_fqn: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/certifications/{target_fqn}", body) or {}

    def recertification_queue(self, **params: Any) -> list[dict[str, Any]]:
        """Certifications at or past their expiry."""
        return rows(self._get("/recertification-queue", **params))

    def proposals(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Changes an agent has proposed and a human has not yet decided."""
        return rows(self._get("/proposals", limit=limit))
