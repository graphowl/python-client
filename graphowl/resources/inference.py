"""What can be derived, and why.

**An inference the SDK cannot explain is a bug in the SDK.** The engine
returns derivations (`/reasoning/explain`), so a client that hands back only
the conclusion has chosen to know less than the server told it — and a
derived fact a reader cannot check is worse than no derived fact, because it
looks like evidence.
"""

from __future__ import annotations

from typing import Any

from ..models import Explanation, InferenceResult, ReasoningRun
from ._base import Resource, rows



class Inference(Resource):
    def run(self, *, graphs: list[str] | None = None, retracted: bool | None = None) -> ReasoningRun:
        """Run the reasoner. Returns *what happened*, not the facts.

        **The endpoint reports counts, and this model matches it rather
        than pretending otherwise.** A `run()` that appeared to return the
        derived facts would be a convenient lie costing a hidden second
        request and disagreeing with the server the moment the run is
        large. Ask `derived(subject=...)` for the facts, and `explain()`
        for one derivation.

        `graphs` selects which named graphs are the asserted base. Leaving
        it unset uses the server's default, which deliberately excludes
        the reasoning graph itself — feeding prior conclusions back in as
        premises makes the next run derive nothing new.
        """
        body: dict[str, Any] = {}
        if graphs:
            body["graphs"] = graphs
        if retracted is not None:
            body["retracted"] = retracted
        payload = self._post("/reasoning/runs", body) or {}
        return ReasoningRun(**{k: v for k, v in payload.items() if k in ReasoningRun.model_fields})

    def derived(self, subject: str) -> list[Any]:
        """Facts held about `subject` that were derived, not asserted.

        `subject` is required by the endpoint and is required here: a
        whole-graph dump of every derived fact is an unbounded query, and
        the SDK does not offer one by accident.
        """
        return rows(self._get("/reasoning/derived", subject=subject))

    def explain(self, subject: str, predicate: str, object: str) -> Explanation | None:
        """The derivation of one fact: the rule, and what it stood on."""
        payload = self._get(
            "/reasoning/explain", subject=subject, predicate=predicate, object=object
        )
        return _explanation(payload) if isinstance(payload, dict) else None

    # ---- the EL profile ----------------------------------------------------
    #
    # A second reasoner for a restricted OWL profile: it can answer
    # subsumption ("is every Invoice a Document?") that the rule-based one
    # cannot, and it terminates where the general case might not. Exposed
    # separately because which reasoner answered is part of the answer.

    def classify(self, **body: Any) -> dict[str, Any]:
        """Compute the class hierarchy under the EL profile."""
        return self._post("/reasoning/el/classify", body) or {}

    def explain_subsumption(self, *, sub: str, sup: str) -> dict[str, Any]:
        """Why one class is held to be a subclass of another.

        The route spells these `subclass` and `superclass`; the parameters
        stay short because that is what a caller writes. The translation
        used to be missing entirely — `sub`/`sup` went to the wire
        unchanged and every call failed on the query string before the
        reasoner saw it.
        """
        return self._get("/reasoning/el/explain", subclass=sub, superclass=sup) or {}


class _ElMixin:
    pass


def _explanation(raw: dict[str, Any]) -> Explanation:
    return Explanation(
        fact=raw.get("fact") or raw.get("conclusion") or "",
        rule=raw.get("rule") or raw.get("ruleId"),
        premises=[p if isinstance(p, str) else str(p) for p in raw.get("premises", [])],
    )
