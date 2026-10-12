"""What actually exists, and what connects to what.

**The storage engine is invisible on purpose.** `owl.graph("demo")`, never a
driver object — that is what leaves GraphOWL free to move between backends
and what stops every consumer growing its own graph machinery
(see the package docstring).

Traversal here is *bounded*. An unbounded whole-graph computation is
`analytics`, a different primitive with different costs and failure modes;
the two are easy to conflate, so they are kept apart.
"""

from __future__ import annotations

from typing import Any

from ..models import Edge, GraphSnapshot, Node, PathSet
from ._base import Resource, rows


#: The serialisations `export` can produce. Listed so a typo fails in the
#: caller's own traceback rather than as a 404 from a path they never see.
EXPORT_FORMATS = ("rdf", "jsonl", "json-graph", "graphml", "cypher", "bulk-csv")

#: What each RDF serialisation is called on the wire. The route parses the
#: body according to `format`, and sending the wrong content type for a
#: document it can otherwise read is an avoidable 400.
RDF_CONTENT_TYPES = {
    "turtle": "text/turtle",
    "json-ld": "application/ld+json",
    "n-triples": "application/n-triples",
    "n-quads": "application/n-quads",
    "rdf-xml": "application/rdf+xml",
}


class Graph(Resource):
    """One named graph. Obtained from `owl.graph("name")`."""

    def __init__(self, transport: Any, name: str | None = None) -> None:
        super().__init__(transport)
        self.name = name

    def entities(self, *, type: str | None = None, limit: int | None = None) -> list[Node]:
        """Instances, optionally of one type."""
        payload = self._get("/assets", type=type, limit=limit, graph=self.name)
        return [_node(row) for row in rows(payload)]

    def subgraph(self, root: str, *, depth: int | None = None, limit: int | None = None) -> GraphSnapshot:
        """A bounded walk outward from `root`.

        Returns a `GraphSnapshot` — nodes, edges, and which of them were
        derived. The SDK renders nothing; the caller draws it. That split
        is why the console and any other application can show the same
        graph without having to agree on a layout library.
        """
        # **`hops` and `maxNodes`, in the route's own spelling.** It is
        # `deny_unknown_fields`, so the `depth`/`limit` this used to send
        # were rejected outright — the bounded call was the broken one and
        # the unbounded call, which every example happened to use, was the
        # only one that worked. `depth` and `limit` stay as the *parameter*
        # names because that is what a caller means; the translation
        # belongs here rather than in their code.
        body: dict[str, Any] = {"seed": root}
        if depth is not None:
            body["hops"] = depth
        if limit is not None:
            body["maxNodes"] = limit
        return _snapshot(self._post("/graph/context", body))

    def query(self, query: str) -> list[dict[str, Any]]:
        """A graph-native query against this graph."""
        return rows(self._post("/sparql", {"query": query}))

    def paths(self, *, source: str, target: str, **options: Any) -> PathSet:
        """Every route between two subjects, shortest first.

        Bounded, like `subgraph`. "No path" and "we stopped looking" are
        different answers and the server distinguishes them.
        """
        return PathSet.model_validate(
            self._post("/graph/paths", {"from": source, "to": target, **options}) or {}
        )

    def analytics(self, *, seed: str, **options: Any) -> dict[str, Any]:
        """Structural measures of the neighbourhood around `seed` —
        in/out degree, orphans, cycles, edge types.

        **Bounded, and it says so.** The walk is capped (`hops`,
        `max_nodes`) and the answer carries `truncated`, so a computation
        that stopped early can never read as a complete one.

        `seed` is any subject, not only a catalog asset: a bare UUID is an
        asset, anything with a colon is a `namespace:local` identifier —
        which is what lets this answer for a tax invoice that has no
        asset row at all.

        **This is not the unbounded whole-graph computation**, and the
        docstring used to say it was. Structural significance over the
        entire graph is a different budget and a different failure mode;
        nothing here computes it, and claiming otherwise made this method
        an example of the exact conflation it warned about.
        """
        return self._post("/graph/context/analytics", {"seed": seed, **options}) or {}

    def reconcile(self, **body: Any) -> dict[str, Any]:
        """Reconcile graph state against a candidate set."""
        return self._post("/graph/reconcile", body) or {}

    # ---- getting data in and out ---------------------------------------

    def import_rdf(
        self, document: str, *, source: str | None = None, format: str = "turtle",
        **params: Any,
    ) -> dict[str, Any]:
        """Load RDF into its own named graph.

        This is the call an application uses to put its own facts into
        GraphOWL — an application lands every upload this way.

        **`source`, not `graph`.** The server takes a source name and
        derives the graph as `graph:import:{source}`; `delete_import`
        retracts by that same source name. Exposing the derived name as
        the input is what let this method sit broken: it used to send a
        JSON object where the route wants the serialised RDF as the
        request body, so every call was a 400.

        The document goes on the wire as-is, under the content type its
        `format` implies, because that is what the route parses.
        """
        if not source:
            from ..exceptions import ValidationError

            raise ValidationError(
                "import_rdf needs source='...' — retraction is scoped to that "
                "name, so an unnamed import could not be undone"
            )
        return self._t.request(
            "POST",
            "/graph/import/rdf",
            content=document.encode("utf-8"),
            headers={"content-type": RDF_CONTENT_TYPES.get(format, "text/turtle")},
            params={"source": source, "format": format, **params},
        ) or {}

    def delete_import(self, **params: Any) -> dict[str, Any]:
        """Retract a previously imported RDF document.

        Reports what it removed. Retraction is scoped to the named graph the
        import wrote into, which is why imports go into their own graph
        rather than the default one — an import that could not be undone
        would make loading somebody else's data a one-way decision.
        """
        source = params.pop("source", None) or params.pop("graph", None)
        if not source:
            from ..exceptions import ValidationError

            raise ValidationError("delete_import needs source='...' — the name the import used")
        return self._t.request(
            "DELETE", "/graph/import/rdf", params={"source": source, **params}
        ) or {}

    def export(self, format: str = "rdf", **params: Any) -> Any:
        """Export the graph.

        `format` is one of the shapes the server serialises to:
        `rdf`, `jsonl`, `json-graph`, `graphml`, `cypher`, `bulk-csv`.
        Named rather than enumerated as six methods, because they differ
        only in serialisation and a caller choosing between them is
        choosing a file format, not an operation.
        """
        if format not in EXPORT_FORMATS:
            from ..exceptions import ValidationError

            raise ValidationError(
                f"{format!r} is not an export format; expected one of {', '.join(EXPORT_FORMATS)}"
            )
        if format == "rdf":
            # `rdf` is the one segment that is not itself a serialisation:
            # turtle, json-ld, n-triples and n-quads all live behind it and
            # the server 400s without being told which. Spelled
            # `rdf_format` rather than `format` because `format` is already
            # this method's first parameter, and one name meaning two
            # different things in one call is how a caller sends turtle to
            # a route expecting `bulk-csv`.
            rdf_format = params.pop("rdf_format", None)
            if rdf_format is None:
                from ..exceptions import ValidationError

                raise ValidationError(
                    "export(format='rdf') needs rdf_format=turtle|json-ld|n-triples|n-quads"
                )
            params["format"] = rdf_format
        return self._t.request(
            "GET", f"/graph/export/{format}", decode=False, params=params or None
        )

    def export_preview(self, **params: Any) -> dict[str, Any]:
        """What an export would contain, without producing it."""
        return self._get("/graph/export/preview", **params) or {}


def _node(row: dict[str, Any]) -> Node:
    return Node(
        # `iri` first: it is the globally unique identity, while `id` is a
        # display-scoped short form that can repeat across graphs.
        id=row.get("iri") or row.get("id") or row.get("subject") or "",
        type=row.get("type") or row.get("kind"),
        label=row.get("label") or row.get("name") or row.get("displayName"),
        properties=row.get("properties") or {},
        # **The server says `derived`; this model says `inferred`.** They
        # are the same idea and the mismatch is a real trap: reading only
        # `inferred` returns False for every edge the reasoner produced,
        # so the flag exists and is always wrong — which is worse than not
        # having it, because it looks authoritative.
        #
        # Absent means asserted. Defaulting the *other* way would mark
        # stated data as derived, inviting a reader to discount a fact
        # somebody actually asserted.
        inferred=bool(row.get("derived", row.get("inferred", False))),
    )


def _edge(row: dict[str, Any]) -> Edge:
    return Edge(
        id=row.get("id"),
        source=row.get("from") or row.get("source") or row.get("subject") or "",
        predicate=row.get("relationship") or row.get("predicate") or row.get("label") or "",
        target=row.get("to") or row.get("target") or row.get("object") or "",
        # See `_node` — the wire field is `derived`.
        inferred=bool(row.get("derived", row.get("inferred", False))),
    )


def _snapshot(payload: Any) -> GraphSnapshot:
    if not isinstance(payload, dict):
        return GraphSnapshot()
    return GraphSnapshot(
        nodes=[_node(n) for n in payload.get("nodes", []) if isinstance(n, dict)],
        edges=[_edge(e) for e in payload.get("edges", []) if isinstance(e, dict)],
        truncated=bool(payload.get("truncated", False)),
    )
