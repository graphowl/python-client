"""What a business term means.

**Deliberately not the same thing as `ontology`.** `vocabulary.term("Invoice")`
answers "what do people here mean by invoice"; `ontology.class_("demo:Invoice")`
answers "what entity type is this, and what can it be connected to". Collapsing
the two is how a catalogue turns back into a database browser — the
distinction is the spine of the whole SDK.
"""

from __future__ import annotations

from typing import Any

from ..models import Term
from ._base import Resource, rows


class Vocabulary(Resource):
    def glossaries(self) -> list[dict]:
        """The glossaries defined in this workspace."""
        return rows(self._get("/glossaries"))

    def terms(self, glossary: str) -> list[Term]:
        """Every term in one glossary.

        Terms live *inside* a glossary on the wire (`/glossaries/{id}/terms`)
        and the SDK does not pretend otherwise: a flat `terms()` across all
        glossaries would have to fan out over an unknown number of
        requests and would quietly change cost as glossaries are added.
        Use `search` for the cross-glossary question.
        """
        return [_term(row) for row in rows(self._get(f"/glossaries/{glossary}/terms"))]

    def term(self, term_id: str) -> Term:
        """One term by id. Raises `NotFoundError` if there is no such term."""
        return _term(self._get(f"/glossary-terms/{term_id}"))

    def search(self, query: str, **params: Any) -> list[Term]:
        """Search terms across every glossary."""
        return [_term(row) for row in rows(self._get("/glossary-terms/search", q=query, **params))]

    def glossary(self, glossary_id: str) -> dict[str, Any]:
        return self._get(f"/glossaries/{glossary_id}") or {}

    def create_glossary(self, **body: Any) -> dict[str, Any]:
        return self._post("/glossaries", body) or {}

    def delete_glossary(self, glossary_id: str) -> None:
        self._delete(f"/glossaries/{glossary_id}")

    def create_term(self, glossary_id: str, **body: Any) -> Term:
        return _term(self._post(f"/glossaries/{glossary_id}/terms", body) or {})

    def update_term(self, term_id: str, **changes: Any) -> Term:
        return _term(self._patch(f"/glossary-terms/{term_id}", changes) or {})

    def delete_term(self, term_id: str) -> None:
        self._delete(f"/glossary-terms/{term_id}")

    # ---- a term's life ---------------------------------------------------

    def relations(self, term_id: str) -> list[dict[str, Any]]:
        """Related, synonymous and broader/narrower terms."""
        return rows(self._get(f"/glossary-terms/{term_id}/relations"))

    def relate(self, term_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/glossary-terms/{term_id}/relations", body) or {}

    def unrelate(self, term_id: str) -> None:
        self._delete(f"/glossary-terms/{term_id}/relations")

    # ---- provenance and proposals -------

    def cite_term(self, term_id: str, *, source_id: str, location: str) -> None:
        """Where this term came from: a registered source, and a place in it.

        **Both halves or neither.** A source with no location says "it came
        from the statute somewhere", which is not something a reviewer can go
        and check — and a definition nobody can check is the thing a glossary
        exists to stop being.

        `location` is the *publisher's* own addressing — "Section 16(2)(b)", a
        page, a clause — never ours, because ours would not survive a reader
        going to look.
        """
        self._post(
            f"/glossary-terms/{term_id}/source",
            {"sourceId": source_id, "location": location},
        )

    def relation_proposals(self) -> list[dict[str, Any]]:
        """Every proposed relation still awaiting a person.

        **A proposal is not a relation.** It is a `candidate`, and every
        approved-only read filters it out — including `relations()` above. A
        proposal that seems to have vanished has not: it is not yet approved.
        """
        return rows(self._get("/relation-proposals"))

    def propose_relation(
        self,
        term_id: str,
        *,
        kind: str,
        target: str,
        passage: str,
        reasoning: str,
    ) -> dict[str, Any]:
        """Propose a relation, with the evidence for it.

        **The evidence is required, and a confidence score is not accepted in
        its place.** A number is not calibrated and not comparable between
        runs; a quoted `passage` and the `reasoning` from it are what a
        reviewer can actually weigh. A passage with no reasoning makes them
        reconstruct the argument themselves.
        """
        return self._post(
            f"/glossary-terms/{term_id}/relation-proposals",
            {
                "kind": kind,
                "target": target,
                "evidence": {"passage": passage, "reasoning": reasoning},
            },
        ) or {}

    def decide_relation(
        self, term_id: str, *, kind: str, target: str, state: str
    ) -> None:
        """Approve or reject one proposed relation.

        `state` is `"approved"` or `"rejected"`. `"candidate"` is refused —
        "nobody has looked at this yet" is not something a decision can make
        true again.
        """
        self._patch(
            f"/glossary-terms/{term_id}/relation-proposals",
            {"kind": kind, "target": target, "state": state},
        )

    def usage(self, term_id: str) -> list[dict[str, Any]]:
        """Where this term is applied — which assets claim to mean it.

        This is the link that makes a glossary worth keeping: a definition
        nothing points at is a document, not metadata.
        """
        return rows(self._get(f"/glossary-terms/{term_id}/usage"))

    def apply_to(self, term_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/glossary-terms/{term_id}/usage", body) or {}

    def remove_usage(self, term_id: str) -> None:
        self._delete(f"/glossary-terms/{term_id}/usage")

    def reviewers(self, term_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/glossary-terms/{term_id}/reviewers"))

    def set_reviewers(self, term_id: str, reviewers: Any) -> Any:
        return self._put(f"/glossary-terms/{term_id}/reviewers", reviewers)

    def transition(self, term_id: str, **body: Any) -> dict[str, Any]:
        """Move a term through its workflow — draft, in review, approved.

        A transition rather than a status field, because who moved it and
        when is the part an auditor asks about.
        """
        return self._post(f"/glossary-terms/{term_id}/transitions", body) or {}

    # ---- business metrics -------------------------------------------------
    #
    # A metric is a *defined number* — "net ITC eligible" — as opposed to a
    # term, which is a defined word. Kept here rather than in its own
    # primitive because both answer "what does this mean", which is what
    # `vocabulary` is for.

    def metrics(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/business-metrics", **params))

    def metric(self, metric_id: str) -> dict[str, Any]:
        return self._get(f"/business-metrics/{metric_id}") or {}

    def search_metrics(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/business-metrics/search", q=query, **params))

    def create_metric(self, **body: Any) -> dict[str, Any]:
        return self._post("/business-metrics", body) or {}

    def update_metric(self, metric_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/business-metrics/{metric_id}", changes) or {}

    def delete_metric(self, metric_id: str) -> None:
        self._delete(f"/business-metrics/{metric_id}")

    def set_metric_sources(self, metric_id: str, sources: Any) -> Any:
        """Which assets this metric is computed from.

        A PUT: the source set is a complete statement. A metric whose
        provenance is half-declared is worse than one with none, because
        it looks traced.
        """
        return self._put(f"/business-metrics/{metric_id}/sources", sources)


    # ---- history and mapping proposals ----------------------------------------

    def glossary_amendments(self, glossary_id: str) -> list[dict[str, Any]]:
        """Every amendment to a glossary's terms, newest first."""
        return rows(self._get(f"/glossaries/{glossary_id}/amendments"))

    def glossary_transitions(self, glossary_id: str) -> list[dict[str, Any]]:
        """Every lifecycle transition in a glossary: who moved which term, when."""
        return rows(self._get(f"/glossaries/{glossary_id}/transitions"))

    def glossary_citations(self, glossary_id: str) -> list[dict[str, Any]]:
        """Every cited term in a glossary: which source, and the place in it."""
        return rows(self._get(f"/glossaries/{glossary_id}/citations"))

    def glossary_health(self, glossary_id: str) -> dict[str, Any]:
        """A glossary's vocabulary health: each issue (SKOS integrity,
        qSKOS), the terms it names and what fixes it."""
        return self._get(f"/glossaries/{glossary_id}/health") or {}

    def term_amendments(self, term_id: str) -> list[dict[str, Any]]:
        """One term's amendments, newest first."""
        return rows(self._get(f"/glossary-terms/{term_id}/amendments"))

    def propose_term_mapping(self, term_id: str, **body: Any) -> dict[str, Any]:
        """Propose what a term becomes in OWL (its kind, domain, range); a
        person decides it with `decide_mapping_proposal`."""
        return self._post(f"/glossary-terms/{term_id}/mapping-proposals", body) or {}

    def mapping_proposals(self, **params: Any) -> list[dict[str, Any]]:
        """Open OWL-mapping proposals across glossaries."""
        return rows(self._get("/mapping-proposals", **params))

    def decide_mapping_proposal(self, proposal_id: str, **body: Any) -> dict[str, Any]:
        """Approve or reject a mapping proposal."""
        return self._patch(f"/mapping-proposals/{proposal_id}", body) or {}


def rows(payload: object) -> list[dict]:
    """A list response, whichever envelope it arrived in.

    The API pages some collections (`{"items": [...]}`) and returns others
    bare. Handling both here means no caller writes that branch, and a
    collection that gains paging later does not break them.
    """
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "terms"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


def _term(row: dict) -> Term:
    return Term(
        id=row.get("id"),
        name=row.get("name") or row.get("term") or "",
        definition=row.get("definition") or row.get("description"),
        synonyms=list(row.get("synonyms") or []),
    )
