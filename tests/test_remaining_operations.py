"""The operations the server offered that no SDK method reached.

Each one here was on `tools/coverage.py`'s missing list. A thin method is
still a contract: the verb and the path have to be the server's, which is
what these assert, one call each.
"""

import json

import httpx
import pytest

from graphowl import GraphOWL


def _client():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    return GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)), seen


CALLS = [
    (lambda o: o.ops.embed_subjects(), "POST", "/admin/search/embed-subjects"),
    (lambda o: o.validation.forget_findings(rule="r1"), "POST", "/findings/forget"),
    (lambda o: o.vocabulary.glossary_amendments("g1"), "GET", "/glossaries/g1/amendments"),
    (lambda o: o.vocabulary.glossary_transitions("g1"), "GET", "/glossaries/g1/transitions"),
    (lambda o: o.vocabulary.glossary_citations("g1"), "GET", "/glossaries/g1/citations"),
    (lambda o: o.vocabulary.glossary_health("g1"), "GET", "/glossaries/g1/health"),
    (lambda o: o.mapping.source_stages("shop"), "GET", "/services/shop/stages"),
    (lambda o: o.mapping.source_intent("shop"), "GET", "/services/shop/intent"),
    (lambda o: o.mapping.source_coverage("shop"), "GET", "/services/shop/coverage"),
    (lambda o: o.mapping.source_metrics("shop"), "GET", "/services/shop/metrics"),
    (lambda o: o.mapping.decide_source_intent("shop", ratify=["a"]), "POST", "/services/shop/intent"),
    (lambda o: o.mapping.add_source_to_workspace("shop", "retail"), "POST", "/services/shop/workspace"),
    (lambda o: o.vocabulary.term_amendments("t1"), "GET", "/glossary-terms/t1/amendments"),
    (lambda o: o.vocabulary.propose_term_mapping("t1", kind="class"), "POST", "/glossary-terms/t1/mapping-proposals"),
    (lambda o: o.vocabulary.mapping_proposals(), "GET", "/mapping-proposals"),
    (lambda o: o.vocabulary.decide_mapping_proposal("m1", decision="approved"), "PATCH", "/mapping-proposals/m1"),
    (lambda o: o.ontology.imports(), "GET", "/ontology-imports"),
    (lambda o: o.ontology.keep_import(document="<a> <b> <c> ."), "POST", "/ontology-imports"),
    (lambda o: o.ontology.resolve_imports(document="x"), "POST", "/ontology-imports/resolve"),
    (lambda o: o.ontology.remove_import("i1"), "DELETE", "/ontology-imports/i1"),
    (lambda o: o.ontology.compare_import("i1", "demo"), "POST", "/ontology-imports/i1/compare/demo"),
    (lambda o: o.ontology.compare("demo", document="x"), "POST", "/ontology-packs/demo/compare"),
    (lambda o: o.ontology.queue_conflicts("demo", document="x"), "POST", "/ontology-packs/demo/conflicts/queue"),
    (lambda o: o.ontology.merge("demo", document="x", plan={}), "POST", "/ontology-packs/demo/merge"),
    (lambda o: o.ontology.import_glossary("demo", document="x", fileName="g.csv"), "POST", "/packs/demo/import/glossary"),
    (lambda o: o.ontology.axiom_proposals("demo"), "GET", "/packs/demo/axiom-proposals"),
    (lambda o: o.ontology.propose_axiom("demo", axiom={}), "POST", "/packs/demo/axiom-proposals"),
    (lambda o: o.ontology.decide_axiom("demo", "a1", decision="approved"), "PATCH", "/packs/demo/axiom-proposals/a1"),
    (lambda o: o.ontology.competency_coverage("demo"), "GET", "/packs/demo/competency-coverage"),
    (lambda o: o.ontology.definition_drift("demo"), "GET", "/packs/demo/definition-drift"),
    (lambda o: o.ontology.apply_definition_drift("demo"), "POST", "/packs/demo/definition-drift/apply"),
    (lambda o: o.ontology.pack_glossary("demo"), "GET", "/packs/demo/glossary"),
    (lambda o: o.ontology.pack_axioms("demo"), "GET", "/packs/demo/axioms"),
    (lambda o: o.ontology.pack_expectations("demo"), "GET", "/packs/demo/expectations"),
    (lambda o: o.ontology.write_pack_glossary("demo", turtle="x"), "PUT", "/packs/demo/glossary"),
    (lambda o: o.ontology.pack_queries("demo"), "GET", "/packs/demo/queries"),
    (lambda o: o.ontology.suggest_owl_model("demo"), "POST", "/packs/demo/suggest-owl-model"),
    (lambda o: o.query.search_nodes("invoice"), "GET", "/search/nodes"),
    (lambda o: o.query.node_embedding("demo:Invoice"), "GET", "/search/nodes/embedding"),
    (lambda o: o.query.similar_nodes("demo:Invoice"), "GET", "/search/nodes/similar"),
    (lambda o: o.workspaces.disable_pack("acme", "demo"), "DELETE", "/workspaces/acme/packs/demo"),
    (lambda o: o.workspaces.graphs("acme"), "GET", "/workspaces/acme/graphs"),
    (lambda o: o.mapping.source_checks("shop"), "GET", "/services/shop/checks"),
    (lambda o: o.mapping.write_source_expectations("shop", ["Orders.ordersCustomers.class"]), "POST", "/services/shop/expectations"),
]


@pytest.mark.parametrize(("call", "method", "path"), CALLS, ids=[c[2] + " " + c[1] for c in CALLS])
def test_each_operation_reaches_its_own_verb_and_path(call, method: str, path: str) -> None:
    owl, seen = _client()
    call(owl)
    assert (seen[0].method, seen[0].url.path) == (method, path)


def test_a_search_carries_its_question_as_a_parameter() -> None:
    owl, seen = _client()
    owl.query.search_nodes("late filing penalty", limit=5)
    assert dict(seen[0].url.params) == {"q": "late filing penalty", "limit": "5"}


def test_a_body_is_sent_as_given() -> None:
    owl, seen = _client()
    owl.ontology.merge("demo", document="doc", plan={"conceptMappings": []})
    assert json.loads(seen[0].content) == {"document": "doc", "plan": {"conceptMappings": []}}
