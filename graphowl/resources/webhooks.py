"""Events in and events out.

Two directions that share a name and almost nothing else:

- **inbound** (`receive`, `mappings`) — another system pushes events at
  GraphOWL, and a mapping turns their payload into facts. This is ingestion
  with someone else holding the schedule.
- **outbound** (`endpoints`, `admin`) — GraphOWL pushes to somebody else
  when something changes.

Dead letters and replay are here because delivery fails, and a system that
cannot show you what it failed to deliver is asking to be trusted about
something it has no evidence for.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows


class Webhooks(Resource):
    # ---- inbound -------------------------------------------------------------

    def mappings(self, name: str) -> dict[str, Any]:
        """How an inbound payload becomes facts."""
        return self._get(f"/webhooks/mappings/{name}") or {}

    def create_mapping(self, **body: Any) -> dict[str, Any]:
        return self._post("/webhooks/mappings", body) or {}

    def dry_run_mapping(self, name: str, **body: Any) -> dict[str, Any]:
        """What a payload *would* produce, without writing anything.

        The same discipline as shape preview and policy dry-run: a
        transformation nobody has watched run is one nobody can vouch for.
        """
        return self._post(f"/webhooks/mappings/{name}/dry-run", body) or {}

    def mapping_versions(self, name: str) -> list[dict[str, Any]]:
        """Every version of a mapping. A payload interpreted differently
        last month is the first thing to check when old facts look wrong."""
        return rows(self._get(f"/webhooks/mappings/{name}/versions"))

    def receive(self, path: str, payload: Any) -> Any:
        """Deliver an event as an external system would.

        Present so an integration can be tested end to end from the same
        client that reads the result, rather than through curl.
        """
        return self._post(f"/webhooks/receive/{path}", payload)

    def event(self, event_id: str) -> dict[str, Any]:
        return self._get(f"/webhooks/events/{event_id}") or {}

    # ---- outbound -------------------------------------------------------------

    def endpoints(self) -> list[dict[str, Any]]:
        return rows(self._get("/webhooks/endpoints"))

    def add_endpoint(self, **body: Any) -> dict[str, Any]:
        return self._post("/webhooks/endpoints", body) or {}

    def outbound(self) -> list[dict[str, Any]]:
        return rows(self._get("/admin/outbound-webhooks"))

    def add_outbound(self, **body: Any) -> dict[str, Any]:
        return self._post("/admin/outbound-webhooks", body) or {}

    def deliveries(self, webhook_id: str) -> list[dict[str, Any]]:
        """What was sent, and what came back."""
        return rows(self._get(f"/admin/outbound-webhooks/{webhook_id}/deliveries"))

    # ---- when delivery fails ----------------------------------------------------

    def dead_letters(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/webhooks/dead-letters", **params))

    def purge_dead_letters(self) -> None:
        self._delete("/webhooks/dead-letters")

    def replay(self, **body: Any) -> dict[str, Any]:
        return self._post("/webhooks/replay", body) or {}
