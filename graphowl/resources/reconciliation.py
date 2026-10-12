"""Where two sides that should agree do not.

**This is the boundary that keeps an application an application rather than the
product.** Reconciliation is a GraphOWL capability; a tax reconciliation
tool is one consumer of it. If a domain application has to reach past this
into the engine, the boundary is drawn in the wrong place — that test is
the reason this primitive exists at all.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows



class Reconciliation(Resource):
    def queue(self) -> list[dict[str, Any]]:
        """Candidate matches awaiting a human decision."""
        return rows(self._get("/resolution/queue"))

    def confirm(self, candidate_id: str) -> dict[str, Any]:
        """Confirm that two records are the same real-world thing."""
        return self._post(f"/resolution/queue/{candidate_id}/confirm", {}) or {}

    def reject(self, candidate_id: str) -> dict[str, Any]:
        """Reject a candidate match.

        A rejection is a *decision*, not a deletion — it is recorded so
        the same pair is not re-proposed, which is the whole reason the
        queue converges instead of re-asking every run.
        """
        return self._post(f"/resolution/queue/{candidate_id}/reject", {}) or {}

    def bulk_decide(self, **body: Any) -> dict[str, Any]:
        """Decide many candidates at once.

        The queue is the bottleneck in practice — a reviewer working one
        pair at a time through a thousand candidates is why entity
        resolution stalls — so the bulk path is a first-class method, not
        a loop the caller writes.
        """
        return self._post("/resolution/queue/bulk", body) or {}

    def review_contradiction(self, **body: Any) -> dict[str, Any]:
        """Record a decision about a contradiction."""
        return self._post("/contradictions/reviews", body) or {}

    def split_merge(self, merge_id: str, **body: Any) -> dict[str, Any]:
        """Undo a merge that turned out to be wrong.

        Resolution is reversible on purpose: a confident wrong merge is
        the most expensive mistake this subsystem can make, and a system
        that cannot undo one makes people reluctant to confirm anything.
        """
        return self._post(f"/merges/{merge_id}/split", body) or {}

    # ---- proposals -----------------------------------------------------------
    #
    # What an agent or a rule suggests, waiting on a person. Two flavours:
    # `proposals` are metadata changes, `change-proposals` hang off an
    # asset. Both are listed because the API keeps them apart and
    # pretending otherwise would hide one of them.

    def proposals(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/proposals", **params))

    def proposal(self, proposal_id: str) -> dict[str, Any]:
        return self._get(f"/proposals/{proposal_id}") or {}

    def accept_proposal(self, proposal_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/proposals/{proposal_id}/accept", body) or {}

    def reject_proposal(self, proposal_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/proposals/{proposal_id}/reject", body) or {}

    def change_proposals(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/change-proposals", **params))

    def accept_change(self, proposal_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/change-proposals/{proposal_id}/accept", body) or {}

    def reject_change(self, proposal_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/change-proposals/{proposal_id}/reject", body) or {}

    def conflicts(self, asset_id: str) -> list[dict[str, Any]]:
        """Contradictions on one asset — two sources asserting
        incompatible things about the same subject.

        Per-asset because that is what the API offers, and because a
        whole-graph contradiction dump is an unbounded query the SDK
        should not make look cheap.
        """
        return rows(self._get(f"/assets/{asset_id}/contradictions"))
