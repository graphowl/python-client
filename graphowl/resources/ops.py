"""Running the thing: partitions, federation, backups, streaming, telemetry.

**A separate sub-client rather than methods scattered through the product
primitives, and that is the whole design decision.** `owl.assets` answers
questions about the catalogue; `owl.ops` answers questions about the
*server*. Folding `compact()` into `catalog` would put a storage-maintenance
operation next to `tables()` as if they were the same kind of thing, and the
person who reaches for one is almost never the person who reaches for the
other.

Exposed at all — rather than left as curl-only admin URLs — because Plan
131's audit found them registered, tested, reachable on the public port and
invisible to every client. A capability that stops at the router is a URL
nobody is told about, and an operational capability nobody is told about is
one that gets rediscovered during an incident.

Most of these require an admin principal. The server enforces that; the SDK
does not second-guess it, so an unauthorised call raises `RefusedError` with
the server's own reason rather than a guess made client-side.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows


class Ops(Resource):
    # ---- storage ---------------------------------------------------------

    def partition_health(self) -> dict[str, Any]:
        """How the flake partitions are holding up.

        The signal that compaction is overdue: reads slow as `flakes_delta`
        grows against `flakes_main`, and this is where that shows before it
        shows as a latency complaint.
        """
        return self._get("/admin/partition-health") or {}

    def compact(self, **body: Any) -> dict[str, Any]:
        """Fold a batch of deltas into the main table."""
        return self._post("/admin/compact", body) or {}

    # ---- backup and restore ----------------------------------------------

    def export(self, **body: Any) -> dict[str, Any]:
        """Take a backup.

        Distinct from `owl.graph().export(...)`, which serialises the graph
        for another tool to read. This is the operational one — the thing
        `restore` consumes.
        """
        return self._post("/admin/export", body) or {}

    def restore(self, **body: Any) -> dict[str, Any]:
        """Load a backup. Read the operations runbook before calling this."""
        return self._post("/admin/restore", body) or {}

    # ---- other surfaces --------------------------------------------------

    def bolt_status(self) -> dict[str, Any]:
        """Whether the Bolt protocol server is up, and what it is serving.

        Bolt is a separate wire protocol on its own port — outside this
        SDK's reach by design — so its *status* being readable over HTTP is
        the only way an HTTP client can see it at all.

        **Only present when the server was built with the `bolt` feature.**
        The contract deliberately does not promise it, since a default
        build does not serve it; against such a build this raises rather
        than returning an empty status, which is the honest answer to "is
        Bolt up" when the endpoint does not exist.
        """
        return self._get("/admin/bolt/status") or {}

    def federation(self) -> dict[str, Any]:
        """Peers this deployment federates with."""
        return self._get("/admin/federation") or {}

    def asset_health(self, fqn: str) -> dict[str, Any]:
        """One asset's freshness and check status, by name.

        Deliberately not `/health`, which is the load balancer's liveness
        probe and says nothing about data. The two share a word and mean
        entirely different things — one asks "is the process up", this asks
        "is this table trustworthy today".
        """
        return self._get(f"/health/{fqn}") or {}

    # ---- streaming --------------------------------------------------------

    def subscriptions(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/streaming/subscriptions", **params))

    def subscribe(self, **body: Any) -> dict[str, Any]:
        return self._post("/streaming/subscriptions", body) or {}

    def dead_letters(self, **params: Any) -> list[dict[str, Any]]:
        """Events the stream could not deliver.

        Separate from `owl.webhooks.dead_letters()`: that is HTTP delivery
        failing, this is the streaming consumer failing. Same idea, two
        transports, and merging them would lose which one broke.
        """
        return rows(self._get("/streaming/dead-letters", **params))

    def replay_dead_letter(self, event_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/streaming/dead-letters/{event_id}/replay", body) or {}

    def replay(self, **body: Any) -> dict[str, Any]:
        """Replay a range of events, rather than one dead letter."""
        return self._post("/streaming/replay", body) or {}

    # ---- telemetry ---------------------------------------------------------

    def tool_usage(self, hours: int | None = None) -> list[dict[str, Any]]:
        """Which MCP tools agents have called, and how often they failed.

        The measured version of "are the agents working" — the console's
        Agents screen is built on exactly this.
        """
        return rows(self._get("/mcp/usage", hours=hours))

    def embed_subjects(self, **body: Any) -> dict[str, Any]:
        """Refresh the subject embeddings semantic node search ranks by.
        Admin only."""
        return self._post("/admin/search/embed-subjects", body) or {}

    def tool_calls(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Individual MCP tool calls, newest first, with why each failed."""
        return rows(self._get("/mcp/calls", limit=limit))
