"""How a source becomes canonical.

The semantic integration layer: a column called `supplier_tax_id` in
somebody's warehouse becomes `demo:Taxpayer.tax_id` here, once, and every
downstream question is asked in the canonical vocabulary instead of in each
source's spelling.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ._base import Resource, rows


def _segment(value: str) -> str:
    """One path segment, escaped whole — a service may be named `demo shop`
    or `a/b`, and neither may split or reshape the path."""
    return quote(value, safe="")

#: Distinguishes "caller said nothing" from "caller said None". `None` is a
#: real choice here — it means send no key — so it cannot double as the
#: default.
_DERIVE = "\x00derive-from-body"


def _content_key(body: object) -> str:
    """A stable key for this exact request body.

    `sort_keys` so two dicts that differ only in insertion order are one
    push, and `default=str` so a date or Decimal in the payload does not
    make the key unserialisable — the key only has to be stable and
    collision-resistant, not reversible.
    """
    import hashlib
    import json

    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]



class Mapping:
    """One source-to-target mapping, built up field by field."""

    def __init__(self, resource: MappingResource, source: str, target: str) -> None:
        self._r = resource
        self.source = source
        self.target = target

    def map_field(self, field: str, to: str) -> dict[str, Any]:
        """Record that a source field means a canonical property.

        Filed as an alignment — a *proposal* — because that is the only
        write the API offers here and because it is the right shape: a
        mapping that applied itself into the canonical vocabulary would be
        the highest-leverage way to corrupt it.
        """
        return self._r._post(
            "/alignments",
            {"source": self.source, "target": self.target, "field": field, "to": to},
        ) or {}

    def map_predicate(self, predicate: str, to: str) -> dict[str, Any]:
        """As `map_field`, for a relationship rather than a value."""
        return self._r._post(
            "/alignments",
            {"source": self.source, "target": self.target, "predicate": predicate, "to": to},
        ) or {}


class MappingResource(Resource):
    def create(self, *, source: str, target: str) -> Mapping:
        return Mapping(self, source, target)

    def align(self, source: str, target: str) -> list[dict[str, Any]]:
        """Propose an alignment between a source schema and an ontology.

        Proposals, not applied mappings. An automatic alignment that wrote
        itself into the canonical vocabulary would be the highest-leverage
        way to corrupt it.
        """
        return rows(self._post("/alignments", {"source": source, "target": target}))

    def alignments(self) -> list[dict[str, Any]]:
        """Proposed alignments awaiting review."""
        return rows(self._get("/alignments/review"))

    def connectors(self) -> list[dict[str, Any]]:
        """Configured sources this workspace pulls from."""
        return rows(self._get("/connectors/configs"))

    def add_connector(self, **body: Any) -> dict[str, Any]:
        """Register a new source connector configuration.

        `connectors()` without a way to add one is read-only by omission
        rather than by design — every workspace has to configure its
        first source somehow, and hand-rolling this one POST defeats the
        point of having the other twelve on this resource.
        """
        return self._post("/connectors/configs", body) or {}

    def runs(self) -> list[dict[str, Any]]:
        """Ingestion runs, newest first."""
        return rows(self._get("/connectors/runs"))

    def connector_schema(self, connector: str) -> dict[str, Any]:
        """What a source currently looks like — the input to a mapping,
        and the thing drift watches for changes."""
        return self._get(f"/connectors/{connector}/schema") or {}

    def test_connector(self, connector: str, **body: Any) -> dict[str, Any]:
        """Check a connector's credentials and reachability before
        scheduling a run against it."""
        return self._post(f"/connectors/{connector}/test", body) or {}

    def run_postgres(self, **body: Any) -> dict[str, Any]:
        return self._post("/connectors/postgres/runs", body) or {}

    # ---- a scanned database, to a reviewed ontology and sampled rows ---------
    #
    # The scan above catalogues a database's tables and keys; these
    # three turn that into a graph: propose it as draft ontology terms (review
    # happens in the Modeller, like any term), then load a bounded sample of
    # the approved tables' rows as instances.

    def save_connection(
        self,
        service: str,
        *,
        host: str,
        database: str,
        username: str,
        password: str | None = None,
        port: int = 5432,
    ) -> dict[str, Any]:
        """Save a Postgres connection once, under the service name. The
        password is write-only: the server never returns it, and loads,
        re-scans and agents then reach the source by name alone."""
        body: dict[str, Any] = {
            "connector": "postgres",
            "serviceName": service,
            "settings": {"host": host, "port": port, "database": database, "username": username},
        }
        if password is not None:
            body["secret"] = password
        return self._post("/connectors/configs", body) or {}

    def source_status(self, service: str) -> dict[str, Any]:
        """Where a scanned database stands: its tables with their keys and
        each class's review status, its terms by status, and how many facts
        are loaded."""
        return self._get(f"/services/{_segment(service)}/status") or {}

    def source_stages(self, service: str) -> dict[str, Any]:
        """Where a source's set-up has got to: its latest run, each stage it
        has passed (latest state, in order) and the stage it resumes at."""
        return self._get(f"/services/{_segment(service)}/stages") or {}

    def add_source_to_workspace(self, service: str, workspace: str) -> dict[str, Any]:
        """Add a scanned source to a workspace: its sample graph, its pack's
        graph and its pack. A workspace gathers many sources; what it already
        holds is kept. Admin only."""
        return self._post(f"/services/{_segment(service)}/workspace", {"workspace": workspace}) or {}

    def source_intent(self, service: str) -> dict[str, Any]:
        """A source's competency questions in words, where each stands, and
        whether the model passes may run (every derived question decided, one
        ratified)."""
        return self._get(f"/services/{_segment(service)}/intent") or {}

    def source_coverage(self, service: str) -> dict[str, Any]:
        """Each kept competency question compiled and run over the source's
        sample: how many are answered, and which have no query yet."""
        return self._get(f"/services/{_segment(service)}/coverage") or {}

    def source_metrics(self, service: str) -> dict[str, Any]:
        """A source's model metrics: classes, properties, axioms by kind, and
        named individuals and instances as two separate figures."""
        return self._get(f"/services/{_segment(service)}/metrics") or {}

    def decide_source_intent(
        self,
        service: str,
        *,
        ratify: list[str] | None = None,
        drop: list[str] | None = None,
        add: list[str] | None = None,
    ) -> dict[str, Any]:
        """Ratify or drop questions by name, or add your own in words
        (ratified as added). Recorded with your name."""
        body = {"ratify": ratify or [], "drop": drop or [], "add": add or []}
        return self._post(f"/services/{_segment(service)}/intent", body) or {}

    def propose_source_ontology(self, service: str) -> dict[str, Any]:
        """Propose every table, column and foreign key as a **draft** term in
        the source's own pack and glossary. Safe to repeat: what already
        exists is reported, not duplicated."""
        return self._post(f"/services/{_segment(service)}/ontology-proposal", {}) or {}

    def source_checks(self, service: str) -> dict[str, Any]:
        """The expectations, mined rules and competency questions a scanned,
        sampled source proposes — each with its evidence. Reads only: write
        the chosen expectations with `write_source_expectations`, and add a
        rule or a question through the pack's own rule and query routes."""
        return self._get(f"/services/{_segment(service)}/checks") or {}

    def write_source_expectations(self, service: str, ids: list[str]) -> dict[str, Any]:
        """Write the chosen expectations (by the ids `source_checks` listed) as
        the source pack's expectations and put them into effect."""
        return self._post(f"/services/{_segment(service)}/expectations", {"ids": ids}) or {}

    def load_source_sample(
        self,
        service: str,
        connection_string: str | None = None,
        tables: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load a bounded sample of the approved tables' rows into the
        source's own graph, replacing the previous sample. `tables` narrows
        it (`"orders"` or `"shop.orders"`); omitted, every approved table
        loads. Omit `connection_string` to use the connection saved for the
        service (`save_connection`); a given one is used for this call only."""
        body: dict[str, Any] = {}
        if connection_string is not None:
            body["connectionString"] = connection_string
        if tables is not None:
            body["tables"] = tables
        return self._post(f"/services/{_segment(service)}/sample-loads", body) or {}

    # ---- pushing metadata in -------------------------------------------------
    #
    # `ingest` is the generic path anything can write to: a scheduler, a
    # lambda, a notebook. The zero-dependency `graphowl-ingest` package
    # exists precisely to be the thing that calls this from inside
    # somebody else's image; this is the same endpoint from the
    # control plane.

    def ingest(
        self, *, idempotency_key: str | None = _DERIVE, **body: Any
    ) -> dict[str, Any]:
        """Push entities and lineage edges, safely retryable.

        **The key is derived from the body by default, not random.** A
        random key makes every retry a new request, which is the behaviour
        the key exists to prevent; the same push twice is the same key, so
        the second is a replay of the first answer rather than a duplicate
        write. The server's own three outcomes are replay, `409` for the
        same key with different content, and `409` while the first is
        still in flight.

        Pass `idempotency_key=None` to send no key — there are pushes
        where a caller genuinely means two identical writes to be two
        writes — and any string to supply your own, which is what you
        want when the natural identity is an upstream batch id rather
        than the bytes.

        Sending a key is also what makes this POST retryable at all: the
        transport retries a keyed push and never an unkeyed one.
        """
        return self._idempotent_post("/ingest", body, idempotency_key) or {}

    def ingest_batch(
        self, *, idempotency_key: str | None = _DERIVE, **body: Any
    ) -> dict[str, Any]:
        """A larger push, same idempotency contract as `ingest`."""
        return self._idempotent_post("/ingest/batch", body, idempotency_key) or {}

    def _idempotent_post(
        self, path: str, body: dict[str, Any], key: str | None
    ) -> Any:
        if key is _DERIVE:
            key = _content_key(body)
        headers = {"Idempotency-Key": key} if key else None
        return self._post(path, body, headers=headers, idempotent=bool(key))

    def ingest_job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/ingest/jobs/{job_id}") or {}

    def cancel_ingest(self, job_id: str) -> None:
        self._delete(f"/ingest/jobs/{job_id}")

    # ---- extraction ------------------------------------------------------------
    #
    # Claims proposed by reading the data itself — a column that looks like
    # a tax ID, a description inferred from usage. Every one is a claim
    # awaiting a decision, never an applied fact.

    def extract(self, **body: Any) -> dict[str, Any]:
        return self._post("/extraction/runs", body) or {}

    def extraction_queue(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/extraction/queue", **params))

    def decide_claim(self, claim_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/extraction/claims/{claim_id}/decision", body) or {}

    def cancel_extraction(self, run_id: str) -> None:
        self._delete(f"/extraction/runs/{run_id}")

    # ---- packs ------------------------------------------------------------------
    #
    # A pack is pure configuration — vocabulary, shapes, rules, queries —
    # and ships no code. That is a load-bearing property of this system,
    # which is why installing one is a data operation rather than a deploy.

    def packs(self) -> list[dict[str, Any]]:
        """Packs available to install."""
        return rows(self._get("/packs/available"))

    def install_pack(self, pack: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/packs/{pack}/install", body) or {}

    def pack_console(self, pack: str) -> dict[str, Any]:
        """A pack's console configuration — the guidance and saved queries
        it ships for the UI to render."""
        return self._get(f"/packs/{pack}/console") or {}

    def pack_queries_run(self, pack: str, query: str, **body: Any) -> Any:
        """Run a query the pack ships, by name."""
        return self._post(f"/packs/{pack}/queries/{query}/run", body)

    def finding_rules(self, pack: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/packs/{pack}/finding-rules"))

    def add_finding_rule(self, pack: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/packs/{pack}/finding-rules", body) or {}

    def pack_candidates(self, pack: str, **body: Any) -> dict[str, Any]:
        """Blocking candidates a pack's matching config proposes."""
        return self._post(f"/packs/{pack}/candidates", body) or {}

    def pack_reconcile(self, pack: str, **body: Any) -> dict[str, Any]:
        """Run a pack's own reconciliation."""
        return self._post(f"/packs/{pack}/reconcile", body) or {}
