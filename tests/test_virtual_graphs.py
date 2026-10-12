"""Virtual graphs: the SDK sends what the server's contract takes, and refuses what would address
another route before anything is sent."""

import json

import httpx
import pytest

from graphowl import GraphOWL, GraphOWLError


def recording(answer: dict) -> tuple[GraphOWL, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)

    return GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)), seen


def test_a_query_sends_the_text_and_its_values_apart_and_returns_the_whole_answer() -> None:
    answer = {"columns": ["lot", "farm"], "rows": [["1", "Ashgrove"]], "truncated": False}
    owl, seen = recording(answer)
    got = owl.virtual_graphs.query("dairy", "MATCH (l:MilkLot) WHERE l.lot_id = $id RETURN l.lot_id", {"id": 1})
    assert got == answer
    assert seen[0].method == "POST" and seen[0].url.path == "/virtual-graphs/dairy/query"
    assert json.loads(seen[0].content) == {
        "query": "MATCH (l:MilkLot) WHERE l.lot_id = $id RETURN l.lot_id",
        "params": {"id": 1},
    }


def test_rows_are_dicts_keyed_by_column_and_a_truncated_answer_raises() -> None:
    owl, _ = recording({"columns": ["lot", "farm"], "rows": [["1", "A"], ["2", "B"]], "truncated": False})
    assert owl.virtual_graphs.rows("dairy", "q") == [{"lot": "1", "farm": "A"}, {"lot": "2", "farm": "B"}]
    cut, _ = recording({"columns": ["lot"], "rows": [["1"]], "truncated": True})
    with pytest.raises(GraphOWLError):
        cut.virtual_graphs.rows("dairy", "q")


def test_a_decision_carries_the_acknowledgement_only_when_given() -> None:
    owl, seen = recording({})
    owl.virtual_graphs.decide("dairy", 1, "approved", "keys are primary")
    owl.virtual_graphs.decide("dairy", 1, "approved", "role is a superuser", acknowledge_writable=True)
    assert "acknowledgeWritable" not in json.loads(seen[0].content)
    assert json.loads(seen[1].content)["acknowledgeWritable"] is True


def test_a_name_that_could_address_another_route_is_refused_before_a_request_is_sent() -> None:
    owl, seen = recording({})
    for bad in ("a/b", "../x", "with space", ""):
        with pytest.raises(GraphOWLError):
            owl.virtual_graphs.query(bad, "q")
    assert seen == []


def test_an_outcome_other_than_approved_or_rejected_is_refused_locally() -> None:
    owl, seen = recording({})
    with pytest.raises(GraphOWLError):
        owl.virtual_graphs.decide("dairy", 1, "maybe", "words")
    assert seen == []


def test_the_audit_trail_and_grants_are_read_from_their_own_paths() -> None:
    owl, seen = recording({"entries": [{"outcome": "ok"}], "role": "app"})
    assert owl.virtual_graphs.log("dairy") == [{"outcome": "ok"}]
    assert owl.virtual_graphs.grants("dairy")["role"] == "app"
    assert [r.url.path for r in seen] == ["/virtual-graphs/dairy/log", "/virtual-graphs/dairy/grants"]
