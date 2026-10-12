"""Whether it is valid.

SHACL is an implementation detail here, and that is the point: a caller
should not have to learn pySHACL's object model to find out that an invoice
is missing a tax ID. They get `result.valid` and a list of violations that
each name a focus node, a path and a message.
"""

from __future__ import annotations

from typing import Any

from ..models import ValidationResult, ValidationRun, Violation
from ._base import Resource, rows



class Validation(Resource):
    def run(self, **options: Any) -> ValidationRun:
        """Run validation now. Returns counts, not the violations.

        The endpoint reports `conforms` plus tallies; the violations
        themselves are paged out of `report()`. Returning an empty list
        here would be worse than returning none — it would read as
        "nothing wrong" on a run that found plenty.
        """
        payload = self._post("/validation/runs", options or {}) or {}
        return ValidationRun(**{k: v for k, v in payload.items() if k in _RUN_KEYS})

    def report(self, *, limit: int | None = None, offset: int | None = None) -> ValidationResult:
        """The violations from the most recent run, without re-running it."""
        payload = self._get("/validation/report", limit=limit, offset=offset) or {}
        violations = [_violation(v) for v in rows(payload)]
        # `valid` is derived from the violations present rather than from a
        # flag: a body claiming conformance while carrying violations is a
        # contradiction, and the violations are the evidence.
        return ValidationResult(valid=not violations, violations=violations)

    def expectations(self) -> list[dict[str, Any]]:
        """Every installed expectation, in words, with the last run's verdict on it.

        **The read that answers "what is this deployment checking".** The
        shapes graph has carried a human name and a why on every rule and
        this is where they reach a caller — `report()` says what
        failed, this says what is being looked for.

        Read-only: the counts are the *last stored run's*, so call `run()`
        first when the data has moved.
        """
        return rows(self._get("/validation/expectations"))

    def shapes_document(self, *, format: str = "turtle") -> str:
        """The SHACL itself — the shapes graph a pass actually runs, as a document.

        `expectations()` is the same graph in words; this is the graph, in the
        form an author can read, copy, or hand back to `shapes_import()`. The
        response is a document, not JSON — `turtle` (the default), `ntriples`,
        `jsonld` or `nquads`.

        `decode=False` because a Turtle body is not JSON and decoding it as
        such raises a parse error that reads as a broken client.
        """
        return self._t.request(
            "GET", "/validation/shapes", params={"format": format}, decode=False
        ) or ""

    #: The only statuses a finding can hold. Named here so a wrong one
    #: fails in the caller's own traceback rather than as a 400 from a
    #: server they may not be able to read the logs of.
    STATUSES = ("pending", "accepted", "rejected")

    # ---- shapes ------------------------------------------------------------

    def shapes_preview(self, **body: Any) -> dict[str, Any]:
        """What a shape set would flag, without storing it.

        The authoring loop: preview, look at what fires, then import. A
        shape imported before anyone has seen what it catches is how a
        workspace acquires 400 violations overnight.
        """
        return self._post("/validation/shapes/preview", body) or {}

    def shapes_import(self, **body: Any) -> dict[str, Any]:
        return self._post("/validation/shapes/import", body) or {}

    def shapes_seed(self, **body: Any) -> dict[str, Any]:
        """Generate starter shapes from what the data already looks like."""
        return self._post("/validation/shapes/seed", body) or {}

    # ---- who fixes it, and what is excused ----------------------------------

    def assign(self, **body: Any) -> dict[str, Any]:
        """Give a violation to someone to fix."""
        return self._post("/validation/assignments", body) or {}

    def unassign(self, assignment_id: str) -> None:
        self._delete(f"/validation/assignments/{assignment_id}")

    def waive(self, **body: Any) -> dict[str, Any]:
        """Excuse a violation, with a reason and an expiry.

        A waiver is a decision that is recorded, not a rule that is
        deleted — which is what lets a reviewer later ask why something
        stopped failing.
        """
        return self._post("/validation/waivers", body) or {}

    def unwaive(self, waiver_id: str) -> None:
        self._delete(f"/validation/waivers/{waiver_id}")

    # ---- findings -----------------------------------------------------------

    def findings(self, *, pack: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """Findings — rule outcomes, decided and undecided.

        `pack` and `status` are the filters the endpoint accepts; a
        `limit` is not one of them and passing it is a 400 rather than a
        silently ignored parameter.

        Note "pending", not "open": the server's vocabulary is
        pending/accepted/rejected, and quietly translating a friendlier
        word here would make the SDK and the console disagree about what
        a finding's state is called.
        """
        if status is not None and status not in self.STATUSES:
            from ..exceptions import ValidationError

            raise ValidationError(
                f"{status!r} is not a finding status; expected one of {', '.join(self.STATUSES)}"
            )
        return rows(self._get("/findings", pack=pack, status=status))

    def decide_finding(self, finding_id: str, **body: Any) -> dict[str, Any]:
        """Accept or reject a finding. This is the human gate."""
        return self._post(f"/findings/{finding_id}/decision", body) or {}

    def finding_evidence(self, finding_id: str) -> Any:
        """The subgraph a finding rests on.

        A finding without its evidence is an accusation. This is what the
        console draws when a reviewer asks "why does it think that".
        """
        from .graph import _snapshot

        return _snapshot(self._get(f"/findings/{finding_id}/evidence-graph"))

    def raise_finding(self, **body: Any) -> dict[str, Any]:
        return self._post("/findings", body) or {}

    # ---- quality tests --------------------------------------------------------
    #
    # Distinct from SHACL shapes, and the distinction is not pedantry. A shape
    # says what the *graph* must look like structurally; a test case says what
    # a *value* must be — row counts, null rates, freshness. Both fail, and
    # they fail for different reasons with different owners.
    #
    # Three nouns: a **definition** is the reusable check ("not null"), a
    # **case** is that definition bound to a column, a **result** is one run of
    # it.

    def test_definitions(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/test-definitions", **params))

    def create_test_definition(self, **body: Any) -> dict[str, Any]:
        return self._post("/test-definitions", body) or {}

    def set_test_cadence(self, definition_id: str, **body: Any) -> dict[str, Any]:
        """How often this definition runs. A check with no cadence is a
        check that ran once and is quietly assumed to still hold."""
        return self._post(f"/test-definitions/{definition_id}/cadence", body) or {}

    def create_test_suite(self, **body: Any) -> dict[str, Any]:
        return self._post("/test-suites", body) or {}

    def test_cases(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/test-cases", **params))

    def create_test_case(self, **body: Any) -> dict[str, Any]:
        return self._post("/test-cases", body) or {}

    def delete_test_case(self, case_id: str) -> None:
        self._delete(f"/test-cases/{case_id}")

    def test_results(self, case_id: str, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get(f"/test-cases/{case_id}/results", **params))

    def record_test_result(self, case_id: str, **body: Any) -> dict[str, Any]:
        """Report a run's outcome.

        Written by whatever executed the check — this catalogue does not run
        your dbt tests, it records what they found, which is why the result
        carries its own timestamp rather than being stamped on arrival.
        """
        return self._post(f"/test-cases/{case_id}/results", body) or {}

    def prune_test_results(self, **body: Any) -> dict[str, Any]:
        """Drop results past their retention window."""
        return self._post("/test-results/prune", body) or {}

    # ---- drift ---------------------------------------------------------------
    #
    # Drift is not validation failing; it is the *shape of the source*
    # changing underneath a mapping that used to be right.

    def drift(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/drift", **params))

    def drift_report(self, **body: Any) -> dict[str, Any]:
        return self._post("/drift/reports", body) or {}

    def apply_drift(self, drift_id: str, **body: Any) -> dict[str, Any]:
        """Accept a detected change into the mapping."""
        return self._post(f"/drift/{drift_id}/apply", body) or {}

    def ignore_drift(self, drift_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/drift/{drift_id}/ignore", body) or {}

    def forget_findings(self, **body: Any) -> dict[str, Any]:
        """Forget findings a withdrawn rule opened (`rule=...`), so a rule
        that no longer exists stops leaving findings behind."""
        return self._post("/findings/forget", body) or {}


_RUN_KEYS = frozenset(
    {"conforms", "violations", "warnings", "info", "shapes", "refusedShapes", "sparqlTruncated"}
)


def _violation(raw: Any) -> Violation:
    if not isinstance(raw, dict):
        return Violation(focus_node="", message=str(raw))
    return Violation(
        focus_node=raw.get("focusNode") or raw.get("focus_node") or raw.get("subject") or "",
        path=raw.get("path") or raw.get("property"),
        message=raw.get("message") or raw.get("detail") or "",
        severity=raw.get("severity"),
    )
