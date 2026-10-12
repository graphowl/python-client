"""Threads, posts, announcements and the inbox.

**Why this is not part of `governance`.** Governance decides what is
*allowed*; this is where people argue about what is *true*. A thread on an
asset — "this column is not what the glossary says" — is the mechanism by
which a catalogue stays honest, and it is the one part of the system whose
content is entirely human.

Memories sit here too, for a reason that is easy to miss: an agent's
recorded conclusion and a person's comment are the same kind of artefact —
someone's claim about a subject, attributable, superseded rather than
edited.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows


class Collaboration(Resource):
    # ---- threads and posts --------------------------------------------------

    # No `thread(id)`: the API exposes a thread through its posts and its
    # asset, not as a document of its own. Reach it via
    # `owl.assets.threads(asset_id)`.

    def posts(self, thread_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/threads/{thread_id}/posts"))

    def reply(self, thread_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/threads/{thread_id}/posts", body) or {}

    def resolve_thread(self, thread_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/threads/{thread_id}/resolve", body) or {}

    def reopen_thread(self, thread_id: str, **body: Any) -> dict[str, Any]:
        """Resolved is not closed. A question that was answered wrongly
        has to be reopenable, or people stop resolving anything."""
        return self._post(f"/threads/{thread_id}/reopen", body) or {}

    def edit_post(self, post_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/posts/{post_id}", changes) or {}

    def delete_post(self, post_id: str) -> None:
        self._delete(f"/posts/{post_id}")

    def reactions(self, post_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/posts/{post_id}/reactions"))

    def react(self, post_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/posts/{post_id}/reactions", body) or {}

    # ---- the inbox -----------------------------------------------------------

    def inbox(self, **params: Any) -> list[dict[str, Any]]:
        """What is waiting on this user: mentions, proposals to decide,
        findings assigned to them."""
        return rows(self._get("/inbox", **params))

    # ---- memories -------------------------------------------------------------

    def memories(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/memories", **params))

    def memory(self, memory_id: str) -> dict[str, Any]:
        return self._get(f"/memories/{memory_id}") or {}

    def record_memory(self, **body: Any) -> dict[str, Any]:
        """Store a durable note about a subject."""
        return self._post("/memories", body) or {}

    def mention(self, memory_id: str, **body: Any) -> dict[str, Any]:
        """Tie a memory to a subject it talks about."""
        return self._post(f"/memories/{memory_id}/mentions", body) or {}

    def retract(self, memory_id: str, **body: Any) -> dict[str, Any]:
        """Withdraw a memory.

        Retracted, not deleted: what somebody believed and when is part of
        the record, and a note that vanishes takes the reason a decision
        was made with it.
        """
        return self._post(f"/memories/{memory_id}/retract", body) or {}

    def supersede(self, memory_id: str, **body: Any) -> dict[str, Any]:
        """Replace a memory with a corrected one, keeping the link."""
        return self._post(f"/memories/{memory_id}/supersede", body) or {}
