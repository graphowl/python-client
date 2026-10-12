"""The nine primitives, and the decisions inside them.

Most of an SDK is plumbing that either works or fails loudly. These are the
places where it can be *quietly* wrong: an inferred edge rendered as
asserted, a truncated walk that looks complete, a `valid: true` sitting on
top of violations.
"""

import httpx
import pytest

from graphowl import GraphOWL, GraphOWLError


def client(routes: dict) -> GraphOWL:
    """A client whose responses are keyed by path."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"detail": f"no route {request.url.path}"})
        return httpx.Response(200, json=body)

    return GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler))


class TestTheThreeStayDistinct:
    """vocabulary / ontology / graph answer different questions."""

    def test_a_vocabulary_term_is_a_definition_not_a_type(self) -> None:
        owl = client({"/glossary-terms/t-1": {"name": "Invoice", "definition": "a demand for payment"}})
        assert owl.vocabulary.term("t-1").definition == "a demand for payment"

    def test_an_ontology_term_carries_its_effective_definition(self) -> None:
        """`effective` is the field that accounts for workspace
        overrides, so reading it means never showing a definition
        somebody has deliberately superseded."""
        owl = client({
            "/ontology-packs": [{"id": "p-1", "packId": "demo"}],
            "/ontology-packs/p-1/terms": [
                {"sourceIri": "demo:Invoice", "term": {"name": "Invoice", "definition": "original"},
                 "effective": {"definition": "the override"}}
            ],
        })
        klass = owl.ontology.class_("demo:Invoice", pack="demo")
        assert klass.label == "Invoice"
        assert klass.definition == "the override"

    def test_a_graph_entity_is_an_instance(self) -> None:
        owl = client({"/assets": [{"iri": "demo:Invoice/123", "type": "demo:Invoice"}]})
        assert owl.graph("demo").entities(type="demo:Invoice")[0].id == "demo:Invoice/123"


class TestInferredIsNeverLost:
    """**The single most misleading thing a graph tool can do** is render a
    derived fact identically to a stated one."""

    def test_a_derived_edge_is_marked_inferred(self) -> None:
        """**The wire says `derived`; the model says `inferred`.** Reading
        only `inferred` returns False for every edge the reasoner
        produced — a flag that exists and is always wrong, which is worse
        than no flag because it looks authoritative."""
        owl = client({"/graph/context": {"nodes": [], "edges": [
            {"from": "a", "relationship": "p", "to": "b", "derived": True}
        ]}})
        snap = owl.graph().subgraph("a")
        assert snap.edges[0].inferred is True
        assert snap.inferred_edges == snap.edges

    def test_an_edge_with_no_flag_is_asserted_not_inferred(self) -> None:
        """Defaulting the other way would mark stated data as derived,
        inviting a reader to discount a fact somebody actually asserted."""
        owl = client({"/graph/context": {"nodes": [], "edges": [
            {"from": "a", "relationship": "p", "to": "b"}
        ]}})
        assert owl.graph().subgraph("a").edges[0].inferred is False

    def test_a_node_carries_its_derived_flag_too(self) -> None:
        owl = client({"/graph/context": {"nodes": [{"id": "n", "derived": True}], "edges": []}})
        assert owl.graph().subgraph("a").nodes[0].inferred is True


class TestABoundedWalkSaysSo:
    def test_truncation_is_reported(self) -> None:
        """"this connects to nothing else" and "we stopped looking" look
        identical without this."""
        owl = client({"/graph/context": {"nodes": [], "edges": [], "truncated": True}})
        assert owl.graph().subgraph("a", depth=1).truncated is True

    def test_a_complete_walk_is_not_marked_truncated(self) -> None:
        owl = client({"/graph/context": {"nodes": [], "edges": []}})
        assert owl.graph().subgraph("a").truncated is False


class TestValidation:
    def test_violations_are_typed_not_raw_dicts(self) -> None:
        owl = client({"/validation/report": {"data": [
            {"focusNode": "demo:Invoice/1", "path": "demo:taxId", "message": "missing", "severity": "Violation"}
        ]}})
        v = owl.validation.report().violations[0]
        assert (v.focus_node, v.path, v.message) == ("demo:Invoice/1", "demo:taxId", "missing")

    def test_a_run_reports_counts_not_an_empty_violation_list(self) -> None:
        """**The endpoint returns `violations` as a number.** Mapping it
        onto a list field would give an empty list on every run that
        found something — "nothing wrong", confidently, on a failing
        graph."""
        owl = client({"/validation/runs": {"conforms": False, "violations": 42, "shapes": 5}})
        run = owl.validation.run()
        assert run.conforms is False
        assert run.violations == 42

    def test_no_violations_is_valid(self) -> None:
        owl = client({"/validation/report": {"data": []}})
        result = owl.validation.report()
        assert result.valid is True
        assert result.summary == "valid"

    def test_expectations_come_back_as_the_rules_in_words(self) -> None:
        """`report()` says what failed; this says what is being looked for.
        The endpoint answers a bare array, which `rows()` handles."""
        owl = client({"/validation/expectations": [
            {"id": "1027:ExpectTaxIdIsTenCharacters",
             "name": "A tax ID is fifteen characters",
             "violations": 0, "warnings": 0, "info": 0}
        ]})
        rules = owl.validation.expectations()
        assert rules[0]["name"] == "A tax ID is fifteen characters"

    def test_the_shapes_document_is_returned_as_a_document_not_json(self) -> None:
        """**A Turtle body decoded as JSON is a parse error that reads as a
        broken client.** `text/turtle` is what this endpoint answers, and the
        caller wants the text — to read, to copy, or to hand back to
        `shapes_import()`."""
        turtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n\nex:OwnedShape a sh:NodeShape .\n"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/validation/shapes"
            assert request.url.params["format"] == "turtle"
            return httpx.Response(200, text=turtle, headers={"content-type": "text/turtle"})

        owl = GraphOWL(
            url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)
        )
        document = owl.validation.shapes_document()
        assert "sh:NodeShape" in document


class TestInferenceExplains:
    def test_an_explanation_names_its_rule_and_premises(self) -> None:
        owl = client({"/reasoning/explain": {
            "fact": "demo:Invoice/123 demo:hasTaxJurisdiction demo:Region",
            "rule": "transitive-jurisdiction",
            "premises": ["demo:Invoice/123 demo:hasSupplier demo:ABC", "demo:ABC demo:registeredIn demo:Region"],
        }})
        explanation = owl.inference.explain("demo:Invoice/123", "demo:hasTaxJurisdiction", "demo:Region")
        assert explanation.rule == "transitive-jurisdiction"
        assert len(explanation.premises) == 2

    def test_a_run_reports_what_happened_and_whether_it_was_partial(self) -> None:
        """A run that hit its budget derived *some* of what follows.
        Reading `derived` alone would take an incomplete closure for a
        complete one."""
        owl = client({"/reasoning/runs": {
            "derived": 231, "iterations": 3, "partial": True, "capped": 5000, "technique": "full"
        }})
        run = owl.inference.run()
        assert run.derived == 231
        assert run.partial is True
        assert run.capped == 5000

    def test_reasoning_over_named_graphs_passes_them_through(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"derived": 0})

        owl = GraphOWL(url="https://api.example", transport=httpx.MockTransport(handler))
        owl.inference.run(graphs=["graph:import:tax_id", "graph:import:books"])
        assert seen["graphs"] == ["graph:import:tax_id", "graph:import:books"]


class TestEnvelopes:
    """The API pages some collections and returns others bare. No caller
    should have to write that branch."""

    @pytest.mark.parametrize("body", [
        [{"name": "Invoice"}],
        {"items": [{"name": "Invoice"}]},
        {"data": [{"name": "Invoice"}]},
        {"results": [{"name": "Invoice"}]},
    ])
    def test_a_list_is_found_in_any_envelope(self, body) -> None:
        """`/validation/report` pages into `data`, `/findings` returns a
        bare list. No caller should write that branch."""
        owl = client({"/glossary-terms/search": body})
        assert [t.name for t in owl.vocabulary.search("x")] == ["Invoice"]

    def test_an_unrecognised_envelope_is_empty_not_a_crash(self) -> None:
        owl = client({"/glossary-terms/search": {"unexpected": "shape"}})
        assert owl.vocabulary.search("x") == []


class TestLazyConstruction:
    def test_sub_clients_are_built_once_and_reused(self) -> None:
        owl = client({})
        assert owl.vocabulary is owl.vocabulary

    def test_a_graph_is_built_per_name(self) -> None:
        owl = client({})
        assert owl.graph("a").name == "a"
        assert owl.graph("b").name == "b"


class TestFindingStatus:
    """The server's vocabulary is pending/accepted/rejected. "open" is a
    400, and it is the word a developer reaches for first."""

    def test_a_wrong_status_fails_before_the_request(self) -> None:
        from graphowl import ValidationError

        owl = client({})
        with pytest.raises(ValidationError) as caught:
            owl.validation.findings(status="open")
        assert "pending" in str(caught.value)

    def test_each_real_status_is_accepted(self) -> None:
        owl = client({"/findings": []})
        for status in ("pending", "accepted", "rejected"):
            assert owl.validation.findings(status=status) == []

    def test_no_status_filter_is_fine(self) -> None:
        owl = client({"/findings": [{"id": "f1"}]})
        assert len(owl.validation.findings()) == 1


class TestTheTwoGapsAMethodBlindCheckMissed:
    """**`coverage.py`'s forward check was path-only, not method-aware.**
    A resource with `PUT /agents/{}/grant` and `DELETE /agents/{}/grant`
    but no `GET` made `GET /agents/{agent_id}/grant` look covered — same
    path, wrong method — and the tool reported 201/201 while two
    operations were genuinely unreachable. Found by an independent audit,
    not by this tool; these pin the fix.
    """

    def test_an_agents_own_grant_can_be_read(self) -> None:
        owl = client({"/agents/system/grant": {"capabilities": ["recordMemory"]}})
        assert owl.governance.get_grant("system")["capabilities"] == ["recordMemory"]

    def test_a_connector_configuration_can_be_added(self) -> None:
        owl = client({})

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/connectors/configs"
            return httpx.Response(200, json={"id": "c-1"})

        owl2 = GraphOWL(url="https://api.example", transport=httpx.MockTransport(handler))
        assert owl2.mapping.add_connector(kind="postgres", host="db")["id"] == "c-1"


class TestAnalyticsIsBoundedAndSaysSo:
    """**Both analytics methods claimed to be something they are not.**

    `graph.analytics()` documented itself as "whole-graph structural
    measures ... over the whole graph", and `assets.analytics()` pointed at
    it as "the unbounded whole-graph form". Neither is true:
    `/graph/context/analytics` takes a required `seed`, walks with
    `Bounds`, and returns a `truncated` flag — it is a bounded
    neighbourhood, the same shape as `subgraph`.

    That is the traversal-vs-analytics conflation this codebase names as a
    standing trap, committed by the docstring that cites the trap. It
    mattered twice over: `seed` was hidden inside `**options`, so the call
    a reader would copy from the docstring — `analytics()` with no
    arguments — reached the server and came back `400`, when the SDK knew
    enough to refuse it without asking.
    """

    def test_a_seed_is_required_at_the_call_site(self) -> None:
        owl = client({})
        with pytest.raises(TypeError):
            owl.graph().analytics()  # type: ignore[call-arg]

    def test_the_seed_is_what_the_server_is_asked_about(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"nodes": [], "truncated": False})

        owl = GraphOWL(
            url="https://api.example", api_key="k",
            transport=httpx.MockTransport(handler),
        )
        owl.graph().analytics(seed="demo:Invoice/1", hops=2)
        assert seen == {"seed": "demo:Invoice/1", "hops": 2}

    def test_truncation_is_reported_rather_than_hidden(self) -> None:
        """A bounded computation that stops early and does not say so is
        the failure mode the whole traversal/analytics split exists for."""
        owl = client({"/graph/context/analytics": {"nodes": ["a"], "truncated": True}})
        assert owl.graph().analytics(seed="a")["truncated"] is True

    def test_neither_docstring_claims_the_whole_graph(self) -> None:
        """Written first as "the phrase must not appear", which the fix
        then failed: the corrected text *denies* whole-graph, and a ban on
        the words cannot tell a claim from its refutation. Asserting on
        the claim is the assertion that was meant."""
        from graphowl.resources.assets import Assets
        from graphowl.resources.graph import Graph

        for method in (Graph.analytics, Assets.analytics):
            assert method.__doc__ is not None
            doc = method.__doc__.lower()
            assert "over the whole graph" not in doc
            assert "bounded" in doc


class TestExportReturnsWhatItExported:
    """**`export()` parsed every format as JSON, and only one is JSON.**

    Measured against the running server, one request per format:

        rdf         400 text/plain            (needs `format=turtle|…`)
        jsonl       200 application/x-ndjson
        json-graph  200 application/json
        graphml     200 application/xml
        cypher      200 text/plain
        bulk-csv    200 application/zstd

    Five of the six are not JSON documents, and the SDK called `.json()`
    on all of them — so `export(format="jsonl")` raised
    `GraphOWLError: 200 response was not JSON` for an export that had
    completely succeeded and was sitting in the response body.

    The fix has to distinguish three things rather than two: a JSON
    document to parse, text to hand back as text, and **bytes**. `bulk-csv`
    is zstd-compressed, so decoding it as UTF-8 corrupts it — a defect that
    would have surfaced as unreadable archives well after the export.
    """

    def _exporting(self, content_type: str, body: bytes) -> GraphOWL:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body, headers={"content-type": content_type})

        return GraphOWL(url="https://api.example", api_key="k",
                        transport=httpx.MockTransport(handler))

    def test_json_graph_is_parsed(self) -> None:
        owl = self._exporting("application/json", b'{"nodes":[],"edges":[]}')
        assert owl.graph().export(format="json-graph") == {"nodes": [], "edges": []}

    def test_ndjson_comes_back_as_text_not_an_exception(self) -> None:
        body = b'{"type":"node","elementId":"1:a"}\n{"type":"node","elementId":"1:b"}\n'
        owl = self._exporting("application/x-ndjson", body)
        exported = owl.graph().export(format="jsonl")
        assert isinstance(exported, str)
        assert exported.count("\n") == 2

    def test_graphml_and_cypher_come_back_as_text(self) -> None:
        assert self._exporting("application/xml", b"<graphml/>").graph().export(
            format="graphml"
        ) == "<graphml/>"
        assert self._exporting("text/plain", b"// generated").graph().export(
            format="cypher"
        ) == "// generated"

    def test_a_compressed_archive_stays_bytes(self) -> None:
        """The one that cannot be papered over by decoding leniently:
        zstd is not text in any encoding."""
        archive = bytes([0x28, 0xB5, 0x2F, 0xFD, 0x00, 0x58, 0x99, 0x00])
        owl = self._exporting("application/zstd", archive)
        assert owl.graph().export(format="bulk-csv") == archive

    def test_the_rdf_serialisation_is_asked_for_by_name(self) -> None:
        """`rdf` is the one path segment that is not itself a
        serialisation — the server 400s without `format`, because turtle,
        json-ld, n-triples and n-quads all live behind it."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, content=b"@prefix : <x> .",
                                  headers={"content-type": "text/turtle"})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        assert owl.graph().export(format="rdf", rdf_format="turtle") == "@prefix : <x> ."
        assert seen == {"format": "turtle"}


class TestSubgraphBoundsReachTheServer:
    """**`subgraph()` sent bounds the route does not accept.**

    `/graph/context` takes `hops` and `maxNodes` and is
    `deny_unknown_fields`; the SDK sent `depth` and `limit`. So the only
    call that worked was the *unbounded* one — asking for `depth=2` came
    back:

        unknown field `depth`, expected one of `seed`, `direction`,
        `hops`, `maxNodes`, `relationshipTypes`, `asOf`

    Every test and every documented example omitted both arguments, which
    is exactly why nothing caught it: the parameters existed in the
    signature, were typed, and went nowhere. Had the route ignored unknown
    fields instead of rejecting them, this would have silently returned a
    default-bounded walk to a caller who asked for a specific one — the
    "truncated walk that looks complete" failure the snapshot type exists
    to prevent.
    """

    def _capturing(self) -> tuple:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"nodes": [], "edges": []})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        return owl, seen

    def test_depth_is_sent_as_hops(self) -> None:
        owl, seen = self._capturing()
        owl.graph().subgraph("demo:Invoice/1", depth=2)
        assert seen == {"seed": "demo:Invoice/1", "hops": 2}

    def test_limit_is_sent_as_max_nodes_in_the_wire_spelling(self) -> None:
        """camelCase, because the route is `deny_unknown_fields` and
        `max_nodes` is as unknown to it as `limit` was."""
        owl, seen = self._capturing()
        owl.graph().subgraph("demo:Invoice/1", limit=50)
        assert seen == {"seed": "demo:Invoice/1", "maxNodes": 50}

    def test_an_unbounded_walk_still_sends_only_the_seed(self) -> None:
        owl, seen = self._capturing()
        owl.graph().subgraph("demo:Invoice/1")
        assert seen == {"seed": "demo:Invoice/1"}


class TestPathsReportsWhatTheServerFound:
    """**`paths()` said "no route" while the server returned three.**

    Found by running the same query twice — once through the SDK, once
    with curl:

        SDK:    []
        server: {"paths": [{"length": 1, "nodes": [...]}, …],
                 "truncated": false}

    `rows()` unwraps `items`/`data`/`results`/`rows`/`nodes`/… and returns
    `[]` for any envelope it does not recognise. `paths` was not in the
    list, so a direct edge between two subjects — `invoice-…INV9001
    reflectedIn 2b-INV-9001-a`, visible in `subgraph()` — was reported as
    unconnected.

    **The silent `[]` is the real defect**, not the missing key: an
    unrecognised envelope and an empty collection are different facts and
    only one of them is "there is nothing there". An SDK that answers the
    wrong question confidently is worse than one that fails.

    And the truncation flag was being discarded, by a method whose own
    docstring promises it: *"No path" and "we stopped looking" are
    different answers and the server distinguishes them.* It did; the SDK
    then threw the distinction away.
    """

    def test_the_paths_the_server_found_are_returned(self) -> None:
        owl = client({"/graph/paths": {
            "paths": [
                {"length": 1, "nodes": ["1024:invoice", "1024:2b-a"]},
                {"length": 2, "nodes": ["1024:invoice", "1024:supplier", "1024:2b-a"]},
            ],
            "truncated": False,
        }})
        found = owl.graph().paths(source="invoice", target="2b-a")
        assert [p.length for p in found.paths] == [1, 2]
        assert found.paths[0].nodes == ["1024:invoice", "1024:2b-a"]

    def test_stopping_early_is_not_the_same_as_finding_nothing(self) -> None:
        exhausted = client({"/graph/paths": {"paths": [], "truncated": True}})
        genuinely_empty = client({"/graph/paths": {"paths": [], "truncated": False}})
        assert exhausted.graph().paths(source="a", target="b").truncated is True
        assert genuinely_empty.graph().paths(source="a", target="b").truncated is False

    def test_an_unrecognised_envelope_is_raised_not_silently_empty(self) -> None:
        """The generalisation. Any future collection that arrives under a
        key `rows()` has never seen must fail loudly, or it becomes this
        same bug wearing a different name."""
        owl = client({"/findings": {"somethingNobodyPlannedFor": [{"id": "f-1"}]}})
        with pytest.raises(GraphOWLError, match="envelope"):
            owl.validation.findings()

    def test_a_genuinely_empty_collection_is_still_empty(self) -> None:
        owl = client({"/findings": {"items": []}})
        assert owl.validation.findings() == []


class TestTheLoudEnvelopeFoundThreeMore:
    """What the `rows()` change turned up the moment it stopped guessing.

    Sweeping every read method against the live server, three answered
    with a shape `rows()` had been silently reducing to `[]`:

        assets.owners()      {"owners": [...]}
        governance.tag_usage()  {"byKind": [...], "total": 0}
        catalog.usage()      {"queriesLast7d": 0, …, "trend": "unknown"}

    The first is a genuine envelope and joins the list. **The other two
    are not collections at all** — they are summary objects that were
    declared `list[dict]`, so `catalog.usage()` answered "no usage
    recorded" for an asset the server had just reported real counts for.
    A wrong return *type* is the more serious of the two faults, and only
    became visible because the silent path was removed.
    """

    def test_owners_arrive_in_their_own_envelope(self) -> None:
        owl = client({"/assets/a-1/owners": {"owners": [{"id": "u-1", "kind": "user"}]}})
        assert owl.assets.owners("a-1") == [{"id": "u-1", "kind": "user"}]

    def test_tag_usage_is_a_summary_not_a_list(self) -> None:
        owl = client({"/tags/demo.pii/usage": {"byKind": [{"kind": "table", "count": 3}], "total": 3}})
        assert owl.governance.tag_usage("demo.pii")["total"] == 3

    def test_asset_usage_reports_the_counts_it_was_given(self) -> None:
        """The one that was actively lying: `[]` read as "nobody queried
        this", for a response carrying four fields of evidence."""
        owl = client({"/usage/orders": {
            "queriesLast7d": 12, "queriesLast30d": 40,
            "distinctConsumers30d": 3, "trend": "rising",
        }})
        assert owl.catalog.usage("orders")["queriesLast7d"] == 12
        assert owl.catalog.usage("orders")["trend"] == "rising"


class TestSubsumptionAsksTheQuestionItWasGiven:
    """**`explain_subsumption(sub=…, sup=…)` sent `sub` and `sup`; the
    route takes `subclass` and `superclass`.**

    Every call failed on the query string before the reasoner saw it:

        Failed to deserialize query string: missing field `subclass`

    The same class of defect as `subgraph()`'s `depth`/`limit` — a typed,
    documented parameter that goes nowhere — and it hid for the same
    reason: both arguments are required here, so *no* call worked and none
    was ever made. A wrapper's parameter names are a translation, and an
    untested translation is a guess.
    """

    def test_the_class_names_reach_the_server_under_its_own_spelling(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"holds": True, "premises": []})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        owl.inference.explain_subsumption(sub="demo:Invoice", sup="demo:Document")
        assert seen == {"subclass": "demo:Invoice", "superclass": "demo:Document"}


class TestTheModelsAnswerTheQuestionsTheyPromise:
    """**Every method here was written with an argument and no test.**

    Mutation testing reported `PathSet.__bool__`, `PathSet.__iter__`,
    `GraphSnapshot.node` and `InferenceResult.explain` as *no tests* — not
    survivors, uncovered. `__bool__` is the sharpest: it exists solely to
    stop a truncated-empty result reading as an honest "no", the rule its
    own docstring states, and inverting `or` to `and` changed nothing that
    any test could see.
    """

    def test_a_truncated_empty_result_is_not_falsy(self) -> None:
        from graphowl.models import PathSet

        assert not PathSet(paths=[], truncated=False)
        # The whole point: the search ran out of budget, so "no paths" is
        # not a finding about the graph and must not read as one.
        assert PathSet(paths=[], truncated=True)

    def test_a_pathset_with_routes_is_truthy_either_way(self) -> None:
        from graphowl.models import Path, PathSet

        one = [Path(length=1, nodes=["a", "b"])]
        assert PathSet(paths=one, truncated=False)
        assert PathSet(paths=one, truncated=True)

    def test_a_pathset_iterates_and_sizes_over_its_paths(self) -> None:
        from graphowl.models import Path, PathSet

        found = PathSet(paths=[Path(length=1, nodes=["a", "b"]),
                               Path(length=2, nodes=["a", "c", "b"])])
        assert len(found) == 2
        assert [p.length for p in found] == [1, 2]

    def test_a_snapshot_finds_a_node_by_id_and_says_when_it_cannot(self) -> None:
        from graphowl.models import GraphSnapshot, Node

        snap = GraphSnapshot(nodes=[Node(id="a"), Node(id="b")])
        assert snap.node("b") is not None
        assert snap.node("b").id == "b"
        assert snap.node("nope") is None

    def test_an_explanation_is_found_by_the_fact_it_explains(self) -> None:
        from graphowl.models import Explanation, InferenceResult

        result = InferenceResult(explanations=[
            Explanation(fact="x", rule="r1"),
            Explanation(fact="y", rule="r2"),
        ])
        assert result.explain("y").rule == "r2"
        assert result.explain("absent") is None


class TestEveryFilterReachesTheWire:
    """**The dominant survivor class, and the generalisation of a bug
    already fixed by hand this session.**

    The largest group of surviving mutants was all one shape: replace an
    argument with `None` at the call site and no test notices.

        payload = self._get("/assets", type=type, limit=limit, graph=self.name)
        payload = self._get("/assets", type=None, limit=limit, graph=self.name)

    Both pass every existing test, because the mocked transport keys on
    *path* and the assertions are about the parsed response. A caller
    asking for `type="table"` would receive every asset and no layer would
    report anything wrong — which is precisely what `subgraph(depth=2)`
    did before it was found by hand, and what a parameter-blind suite
    cannot distinguish from correct behaviour.

    So the assertion is about the request, not the response. One table
    rather than one test per method: the property is uniform, and a
    per-method test would be forty copies of the same three lines with
    forty chances to write one of them wrongly.
    """

    def _sent(self, call) -> httpx.Request:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"items": []})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        call(owl)
        assert seen, "no request was made"
        return seen[0]

    @pytest.mark.parametrize(
        ("call", "expected"),
        [
            (lambda o: o.graph("demo").entities(type="table", limit=5),
             {"type": "table", "limit": "5", "graph": "demo"}),
            (lambda o: o.assets.list(limit=3, offset=6), {"limit": "3", "offset": "6"}),
            (lambda o: o.assets.search("invoice"), {"q": "invoice"}),
            (lambda o: o.validation.findings(pack="demo", status="pending"),
             {"pack": "demo", "status": "pending"}),
            (lambda o: o.vocabulary.search("tax"), {"q": "tax"}),
            (lambda o: o.governance.policies(limit=2), {"limit": "2"}),
            (lambda o: o.ops.tool_usage(24), {"hours": "24"}),
            (lambda o: o.ops.tool_calls(7), {"limit": "7"}),
            (lambda o: o.catalog.search("orders"), {"q": "orders"}),
            (lambda o: o.inference.explain_subsumption(sub="256:A", sup="256:B"),
             {"subclass": "256:A", "superclass": "256:B"}),
        ],
    )
    def test_the_parameters_given_are_the_parameters_sent(self, call, expected) -> None:
        sent = dict(self._sent(call).url.params)
        for key, value in expected.items():
            assert sent.get(key) == value, f"{key}: sent {sent.get(key)!r}, wanted {value!r}"

    def test_an_unset_optional_is_omitted_rather_than_sent_as_null(self) -> None:
        """The other half, and the reason the first half cannot simply
        assert equality: several routes validate their query string
        strictly and answer 400 for a literal `None`, so an argument left
        unset must not reach the wire at all."""
        sent = dict(self._sent(lambda o: o.assets.list()).url.params)
        assert "limit" not in sent
        assert "offset" not in sent


class TestRdfImportSpeaksTheRouteItCalls:
    """**`import_rdf` never worked, and its own docstring said what it was
    for.**

    The route is `POST /graph/import/rdf?source=…&format=turtle` with the
    serialised RDF as the **request body** under `content-type:
    text/turtle`. The SDK sent a JSON object — `{"turtle": ..., "graph":
    ...}` — so every call was a `400`, and `delete_import` passed `graph=`
    where the route reads `source=`.

    Proved by running the same import twice, once with curl and once
    through the SDK: `{"landed": ["1024:nb-INV-9001"], ...}` against
    `ValidationError: 400 Bad Request`.

    Nothing caught it because nothing exercised it. The docstring says
    "an application writes its reconciliation results this way", and an application does
    — by hand-rolling the request correctly against the raw API, which is
    exactly the work this method exists to remove.

    **`source`, not `graph`.** The server names it `source` and derives the
    named graph as `graph:import:{source}`; exposing the derived name as
    the input is what let the mismatch hide.
    """

    def _capturing(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            seen["content_type"] = request.headers.get("content-type", "")
            seen["body"] = request.content.decode()
            return httpx.Response(200, json={"landed": [], "skipped": [], "rejected": []})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        return owl, seen

    def test_the_turtle_is_the_body_not_a_json_field(self) -> None:
        owl, seen = self._capturing()
        turtle = "@prefix demo: <x> .\ndemo:a a demo:B ."
        owl.graph().import_rdf(turtle, source="books-2026-07")
        assert seen["body"] == turtle
        assert seen["content_type"].startswith("text/turtle")

    def test_the_source_and_format_travel_as_query_parameters(self) -> None:
        owl, seen = self._capturing()
        owl.graph().import_rdf("@prefix a: <x> .", source="books-2026-07")
        assert seen["params"] == {"source": "books-2026-07", "format": "turtle"}

    def test_another_serialisation_can_be_named(self) -> None:
        owl, seen = self._capturing()
        owl.graph().import_rdf('{"@id": "x"}', source="s", format="json-ld")
        assert seen["params"]["format"] == "json-ld"
        assert seen["content_type"].startswith("application/ld+json")

    def test_retraction_names_the_same_source_the_import_used(self) -> None:
        owl, seen = self._capturing()
        owl.graph().delete_import(source="books-2026-07")
        assert seen["method"] == "DELETE"
        assert seen["params"] == {"source": "books-2026-07"}

    def test_an_import_with_no_source_is_refused_before_it_is_sent(self) -> None:
        """The server would answer 400; the SDK knows enough to say why."""
        owl, _ = self._capturing()
        with pytest.raises(GraphOWLError, match="source"):
            owl.graph().import_rdf("@prefix a: <x> .")


class TestOntologyInstallSpeaksTheRouteItCalls:
    """**`install` never worked either, same bug class as `import_rdf`.**

    `POST /ontology-packs` (`import_pack`)
    takes the SKOS Turtle document as the **request body**, with `packId`,
    `version`, `sourceUrl`, `licenceKind`, `licenceName` and
    `acknowledgeLicence` as **query parameters** — `deny_unknown_fields` on
    the server side, so an extra or misnamed key 400s rather than being
    ignored. The method used to be `self._post("/ontology-packs", body)`,
    sending the whole thing as a JSON object; every real call would have
    been a 400 the same way `import_rdf` was before its own fix.
    """

    def _capturing(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            seen["content_type"] = request.headers.get("content-type", "")
            seen["body"] = request.content.decode()
            return httpx.Response(201, json={"id": "p-1", "packId": "acme-refunds"})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        return owl, seen

    def test_the_turtle_is_the_body_not_a_json_field(self) -> None:
        owl, seen = self._capturing()
        turtle = "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        owl.ontology.install(
            turtle, pack_id="acme-refunds", version="1.0.0",
            licence_kind="permissive", licence_name="CC0",
        )
        assert seen["body"] == turtle
        assert seen["content_type"] == "text/turtle"
        assert seen["method"] == "POST"
        assert seen["path"] == "/ontology-packs"

    def test_pack_identity_and_licence_travel_as_query_parameters(self) -> None:
        owl, seen = self._capturing()
        owl.ontology.install(
            "@prefix skos: <x> .", pack_id="acme-refunds", version="1.0.0",
            licence_kind="permissive", licence_name="CC0", source_url="https://example.com/acme",
        )
        assert seen["params"] == {
            "packId": "acme-refunds", "version": "1.0.0", "sourceUrl": "https://example.com/acme",
            "licenceKind": "permissive", "licenceName": "CC0", "acknowledgeLicence": "false",
        }

    def test_an_attribution_licence_carries_its_notice(self) -> None:
        owl, seen = self._capturing()
        owl.ontology.install(
            "@prefix skos: <x> .", pack_id="acme-refunds", version="1.0.0",
            licence_kind="attributionRequired", licence_name="CC-BY-4.0",
            licence_notice="Copyright Acme", acknowledge_licence=True,
        )
        assert seen["params"]["licenceNotice"] == "Copyright Acme"
        assert seen["params"]["acknowledgeLicence"] == "true"
        # Unset optional fields never reach the wire — the server's own
        # `deny_unknown_fields` would 400 on a stray `licenceContact=` key
        # sent as an empty string rather than omitted entirely.
        assert "licenceContact" not in seen["params"]


class TestOntologyUninstallDefaultsToADryRun:
    """**`uninstall` looked like it worked and never removed anything.**

    `DELETE /ontology-packs/{id}` always returns a `PackRemovalReport`
    (term count, every source still attached) and only actually deletes
    when `force=true` is on the query string — the same preview-before-
    you-break-it shape as the ontology editor's own preview/dry-run/save
    split. The method used to call `self._delete(path)` with no way to
    pass `force` at all and threw the response away, so every call was
    silently the dry-run branch with no result to notice from.
    """

    def _capturing(self, report):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=report)

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        return owl, seen

    def test_the_dry_run_report_is_returned_not_discarded(self) -> None:
        report = {"termCount": 2, "attachmentCounts": [], "totalAttachments": 0}
        owl, seen = self._capturing(report)
        result = owl.ontology.uninstall("11111111-1111-1111-1111-111111111111")
        assert result == report
        assert seen["params"]["force"] == "false"

    def test_force_travels_to_the_query_string(self) -> None:
        owl, seen = self._capturing({"termCount": 0, "attachmentCounts": [], "totalAttachments": 0})
        owl.ontology.uninstall("11111111-1111-1111-1111-111111111111", force=True)
        assert seen["params"]["force"] == "true"
        assert seen["method"] == "DELETE"
        assert seen["path"] == "/ontology-packs/11111111-1111-1111-1111-111111111111"


class TestAScannedDatabaseBecomesAGraph:
    """scan, propose, review, load, through `owl.mapping`."""

    def _recording(self, answer: dict):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=answer)

        owl = GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler))
        return owl, seen

    def test_a_source_s_status_is_read_by_its_service_name(self) -> None:
        owl, seen = self._recording({"service": "shop", "loadedFacts": 0})
        assert owl.mapping.source_status("demo shop")["service"] == "shop"
        assert (seen[0].method, seen[0].url.raw_path) == ("GET", b"/services/demo%20shop/status")

    def test_proposing_an_ontology_names_the_service_and_nothing_else(self) -> None:
        owl, seen = self._recording({"proposed": 9})
        assert owl.mapping.propose_source_ontology("shop")["proposed"] == 9
        assert (seen[0].method, seen[0].url.path) == ("POST", "/services/shop/ontology-proposal")

    def test_a_sample_load_sends_the_connection_and_only_the_tables_asked_for(self) -> None:
        import json

        owl, seen = self._recording({"added": 14})
        owl.mapping.load_source_sample("shop", "postgres://u:p@h/db", tables=["shop.orders"])
        owl.mapping.load_source_sample("shop", "postgres://u:p@h/db")
        assert seen[0].url.path == "/services/shop/sample-loads"
        assert json.loads(seen[0].content) == {
            "connectionString": "postgres://u:p@h/db",
            "tables": ["shop.orders"],
        }
        assert json.loads(seen[1].content) == {"connectionString": "postgres://u:p@h/db"}, (
            "no tables means every approved table, so none is sent"
        )
        owl.mapping.load_source_sample("shop")
        assert json.loads(seen[2].content) == {}, (
            "no connection string means the one saved on Connectors, so none is sent"
        )

    def test_a_connection_is_saved_once_with_its_password_write_only(self) -> None:
        import json

        owl, seen = self._recording({"id": "c-1", "hasSecret": True})
        owl.mapping.save_connection(
            "shop", host="db", port=5433, database="shop", username="reader", password="pw"
        )
        assert (seen[0].method, seen[0].url.path) == ("POST", "/connectors/configs")
        assert json.loads(seen[0].content) == {
            "connector": "postgres",
            "serviceName": "shop",
            "settings": {"host": "db", "port": 5433, "database": "shop", "username": "reader"},
            "secret": "pw",
        }
