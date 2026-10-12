"""The generated resource: it sends what the contract says and refuses a value that would address another route."""

import json

import httpx
import pytest

from graphowl import GraphOWL, GraphOWLError


def recording() -> tuple[GraphOWL, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    return GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)), seen


def test_a_read_puts_its_ids_in_the_path_and_its_filters_in_the_query() -> None:
    owl, seen = recording()
    owl.modelling.list_complex_alignments(status="proposed")
    owl.modelling.list_glossaries_ontology_model_versions("g-1")
    assert seen[0].url.path == "/complex-alignments" and seen[0].url.params["status"] == "proposed"
    assert seen[1].url.path == "/glossaries/g-1/ontology-model/versions"


def test_a_write_sends_its_body_as_one_object() -> None:
    owl, seen = recording()
    owl.modelling.create_glossaries_ontology_model_generate("g-1")
    owl.modelling.update_wording_proposals("w-9", {"state": "approved"})
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {}
    assert seen[1].method == "PATCH" and json.loads(seen[1].content) == {"state": "approved"}


def test_an_id_that_would_address_another_route_is_refused_before_anything_is_sent() -> None:
    owl, seen = recording()
    for bad in ("a/b", "x?y=1", "", "q#frag"):
        with pytest.raises(GraphOWLError):
            owl.modelling.list_glossaries_ontology_model_versions(bad)
    assert seen == []
