"""What entity types exist, and how they relate.

**Not `vocabulary`.** A vocabulary term is what people mean by a word; an
ontology class is a type with superclasses, properties and constraints. The
SDK keeps them apart because collapsing them is how a semantic layer decays
back into a table browser.

Classes are returned as navigable objects rather than dicts. `invoice.is_a(
"demo:Document")` is the question a caller actually has; making them fetch a
class, find a `superClassOf` key and walk it themselves is handing back the
work the SDK exists to do.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows


class OntologyClass:
    """One class, with its neighbourhood reachable from it."""

    def __init__(self, resource: Ontology, iri: str, raw: dict[str, Any]) -> None:
        self._r = resource
        self.iri = iri
        self.raw = raw

    @property
    def label(self) -> str | None:
        term = self.raw.get("term") or {}
        return self.raw.get("label") or term.get("name") or term.get("label")

    @property
    def definition(self) -> str | None:
        """The effective definition — the pack's own, or an override if a
        workspace has replaced it. `effective` is the field that already
        accounts for that, so reading it means the SDK never shows a
        definition somebody has deliberately superseded."""
        effective = self.raw.get("effective") or {}
        return effective.get("definition") or (self.raw.get("term") or {}).get("definition")

    def superclasses(self) -> list[str]:
        return _iris(self.raw, "superClasses", "subClassOf", "parents")

    def properties(self) -> list[str]:
        return _iris(self.raw, "properties", "attributes")

    def constraints(self) -> list[dict[str, Any]]:
        value = self.raw.get("constraints")
        return list(value) if isinstance(value, list) else []

    def is_a(self, iri: str) -> bool:
        """Whether this class is that one, or descends from it.

        Answered against the *server's* transitive closure where one is
        offered, and against the direct parents otherwise. It never walks
        the hierarchy client-side across several requests: that is slow,
        and it would disagree with the reasoner the moment a subClassOf
        axiom is derived rather than asserted.
        """
        if iri == self.iri:
            return True
        return iri in self.superclasses()

    def __repr__(self) -> str:
        return f"OntologyClass({self.iri!r})"


class Ontology(Resource):
    def packs(self) -> list[dict[str, Any]]:
        """Every ontology pack installed."""
        return rows(self._get("/ontology-packs"))

    def pack(self, pack: str) -> dict[str, Any]:
        """One installed pack, by name or UUID."""
        return self._get(f"/ontology-packs/{self.resolve_pack(pack)}") or {}

    def install(
        self,
        skos_turtle: str,
        *,
        pack_id: str,
        version: str,
        licence_kind: str,
        licence_name: str,
        source_url: str = "",
        licence_notice: str | None = None,
        licence_contact: str | None = None,
        acknowledge_licence: bool = False,
    ) -> dict[str, Any]:
        """Import a brand-new ontology pack from a SKOS/RDFS Turtle document.

        **The Turtle is the request body, not a JSON field** — the same
        shape `graph.import_rdf` needed fixing to match. The route parses
        `skos:prefLabel`/`skos:definition`/`skos:broader` (or their
        `rdfs:label`/`rdfs:subClassOf` aliases) into a new glossary; every
        concept must carry a label, and a `broader` reference must resolve
        to another concept in the same document.

        `licence_kind` is one of `"permissive"`, `"attributionRequired"`
        (needs `licence_notice`) or `"licenceRequired"` (needs
        `licence_contact`) — the licence a pack is imported under is not
        optional metadata here, it gates whether `acknowledge_licence` must
        be `True` before the import is accepted at all.
        """
        params: dict[str, Any] = {
            "packId": pack_id,
            "version": version,
            "sourceUrl": source_url,
            "licenceKind": licence_kind,
            "licenceName": licence_name,
            "licenceNotice": licence_notice,
            "licenceContact": licence_contact,
            "acknowledgeLicence": acknowledge_licence,
        }
        return self._t.request(
            "POST",
            "/ontology-packs",
            content=skos_turtle.encode("utf-8"),
            headers={"content-type": "text/turtle"},
            params={k: v for k, v in params.items() if v is not None},
        ) or {}

    def uninstall(self, pack: str, *, force: bool = False) -> dict[str, Any]:
        """Remove an installed ontology pack.

        **Without `force=True` this is a dry run.** The server always
        reports what removal would affect — the pack's term count, and
        every source still attached to one of its terms — and only
        deletes anything when `force=True` is explicit. The SDK used to
        drop the response and default to the dry-run branch with no way
        to ask for the real thing, so every call looked like it worked
        and nothing was ever actually removed.
        """
        return self._delete(f"/ontology-packs/{self.resolve_pack(pack)}", force=force) or {}

    def upgrade(self, pack: str, **body: Any) -> dict[str, Any]:
        """Move a pack to a newer version.

        Returns what changed. An upgrade that silently reinterpreted
        existing facts would be the most damaging thing a pack can do, so
        the server reports the diff rather than applying it quietly.
        """
        return self._post(f"/ontology-packs/{self.resolve_pack(pack)}/upgrade", body) or {}

    # ---- local overrides ---------------------------------------------------
    #
    # A workspace can override a pack's definitions without forking it.
    # `effective` on a term already accounts for these, which is why
    # `OntologyClass.definition` reads that field and not the pack's own.

    def overrides(self, pack: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/ontology-packs/{self.resolve_pack(pack)}/overrides"))

    def override(self, pack: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/ontology-packs/{self.resolve_pack(pack)}/overrides", body) or {}

    def remove_override(self, pack: str, override_id: str) -> None:
        self._delete(f"/ontology-packs/{self.resolve_pack(pack)}/overrides/{override_id}")

    # ---- the authoring loop ---------------------------------------------------
    #
    # preview -> dry_run -> save, and the order is the whole point. An
    # ontology edit reinterprets facts that already exist: a renamed property
    # or a narrowed domain can silently invalidate every inference that stood
    # on it. Seeing what an edit *would* do before it does it is not a
    # convenience here, it is the only safe way to change a vocabulary that
    # has data underneath it.

    def editor_preview(self, **body: Any) -> dict[str, Any]:
        """Render an edit without validating it against the graph."""
        return self._post("/ontology-editor/preview", body) or {}

    def editor_dry_run(self, **body: Any) -> dict[str, Any]:
        """What this edit would change, and what it would break."""
        return self._post("/ontology-editor/dry-run", body) or {}

    def editor_save(self, **body: Any) -> dict[str, Any]:
        return self._post("/ontology-editor/save", body) or {}

    # ---- pack obligations, queries and rules -----------------------------------

    def pack_obligations(self, pack: str) -> list[dict[str, Any]]:
        """What the pack says must be done, and by when.

        A tax filing deadline is an obligation, not a validation rule: it
        does not fail when data is malformed, it falls due.
        """
        return rows(self._get(f"/packs/{pack}/obligations"))

    def declare_pack_queries(self, pack: str, **body: Any) -> dict[str, Any]:
        """Register the queries a pack ships, by name."""
        return self._post(f"/packs/{pack}/queries", body) or {}

    def delete_finding_rule(self, pack: str, label: str) -> None:
        """Unregister a rule.

        Deliberately explicit rather than inferred from a re-import: there
        is no provenance column that would let a reload safely decide a
        missing rule was *meant* to be gone rather than merely absent from
        one file.
        """
        self._delete(f"/packs/{pack}/finding-rules/{label}")

    def context(self, version: str = "v1") -> dict[str, Any]:
        """The JSON-LD context this deployment publishes.

        What a consumer needs to read GraphOWL's own JSON as linked data:
        which prefixes map to which namespaces. Versioned, because a
        context that changed silently would reinterpret documents already
        written against it.
        """
        return self._get(f"/context/{version}") or {}

    def profile(self) -> dict[str, Any]:
        """Which OWL profile the loaded ontology falls in, and why.

        Not decoration: the profile decides which reasoner can run and
        what it is allowed to conclude, so a caller comparing two
        deployments needs it.
        """
        return self._get("/ontology/profile") or {}

    # ---- authoring, provenance and the file on disk ----------
    #
    # **Nine operations the SDK could not reach** with
    # the five routes that were served and undocumented. Kept on `ontology`
    # rather than a new resource: every one of them is a step in producing a
    # pack — the sources its terms cite, the model compiled to Turtle, the
    # file written, and the bundle that carries all three somewhere else.

    def sources(self) -> list[dict[str, Any]]:
        """Every registered source a term can be cited against."""
        return rows(self._get("/sources"))

    def register_source(
        self,
        *,
        kind: str,
        title: str,
        publisher: str,
        licence: dict[str, Any],
        content: str,
        uri: str | None = None,
        version: str | None = None,
        effective_date: str | None = None,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:
        """Register a source, so a term can say where it came from.

        **`content` is hashed, not stored.** This table records *where a term
        came from*; keeping a copy of every statute would make it a document
        store with a licensing problem of its own. The hash is what makes a
        later amendment detectable.

        `licence` is a tagged object — `{"kind": "permissive", "name": ...}`,
        `{"kind": "attributionRequired", "name": ..., "notice": ...}` or
        `{"kind": "licenceRequired", "name": ..., "contact": ...}`. There is no
        default and no "unknown": a source whose terms are unclear must be
        stated, not guessed permissive.
        """
        body = {
            "kind": kind,
            "title": title,
            "publisher": publisher,
            "licence": licence,
            "content": content,
            "uri": uri,
            "version": version,
            "effectiveDate": effective_date,
            "jurisdiction": jurisdiction,
        }
        return self._post("/sources", {k: v for k, v in body.items() if v is not None}) or {}

    def compile(
        self,
        *,
        namespace: str,
        classes: list[dict[str, Any]] | None = None,
        object_properties: list[dict[str, Any]] | None = None,
        data_properties: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compile a semantic model to Turtle, or be told why it cannot be.

        **Always `200`, and the answer is tagged.** Branch on `kind`:
        `compiled` carries `document` (Turtle) *and* `triples` — what a model
        says is one decision, how it is spelled is presentation, and both are
        returned so a caller can offer four formats without a second copy of
        the rule. `refused` carries `defects`; `error` carries `message`.

        A refusal is a normal outcome of asking, not a failure — the check
        runs before any bytes exist, because a conjunction that reaches a
        compiled document has already manufactured false type facts.

        **`compile` persists nothing.** The document it returns is not in the
        graph and not on disk until `write_ontology_file` and `install` have
        both run.
        """
        return self._post(
            "/ontology/compile",
            {
                "namespace": namespace,
                "classes": classes or [],
                "objectProperties": object_properties or [],
                "dataProperties": data_properties or [],
            },
        ) or {}

    def read_ontology_file(self, pack: str) -> str:
        """A pack's `ontology.ttl`, as Turtle.

        Not decoded: the body is a Turtle document, and parsing it as JSON
        turns a successful read into an exception — the same reason
        `graph.export` stopped decoding.
        """
        body = self._t.request("GET", f"/packs/{pack}/ontology", decode=False)
        return body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)

    def write_ontology_file(
        self, pack: str, turtle: str, *, force: bool = False
    ) -> dict[str, Any]:
        """Write a pack's ontology file — **and read the result, always**.

        This route *replaces* the file, so it refuses a document that would
        drop triples the file already asserts, answering
        `{"kind": "wouldDrop", "count": ..., "dropped": [...]}` with a `200`.
        That is a refusal, not an error: one such write took a real pack's
        ontology from 495 lines to 205 while reporting success.

        **`force=True` is not a retry.** `wouldDrop` means the document is
        missing something the file already has; read `dropped`, find out why,
        and merge. Force only when replacing is genuinely what was intended.
        """
        return self._t.request(
            "PUT",
            f"/packs/{pack}/ontology",
            content=turtle.encode("utf-8"),
            headers={"content-type": "text/turtle"},
            params={"force": force} if force else None,
        ) or {}

    def export_bundle(self, pack: str) -> dict[str, Any]:
        """A pack, its sources and its finding rules, as one re-importable
        document.

        **Not the same thing as an RDF export.** That serializes the facts in
        the graph; a pack is more than its facts — it is the document its
        terms came from, the sources they cite, and the rules that run against
        them. Exporting the triples and calling it a backup loses all three.
        """
        return self._get(f"/ontology-packs/{self.resolve_pack(pack)}/bundle") or {}

    def import_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """Restore a bundle produced by `export_bundle`."""
        return self._post("/ontology-packs/bundle", bundle) or {}

    def reset(self, pack: str, *, force: bool = False) -> dict[str, Any]:
        """Clear a pack so a bundle can be re-imported onto clean ground.

        **Reports by default.** A reset is what somebody runs to find out what
        it would take, so a default that removed would make finding out the
        dangerous option. Nothing is removed until `force=True`.

        **What `uninstall` does not do.** That removes the pack and its terms
        and leaves every finding rule registered and still firing, so a
        re-import lands on top of the previous pack's rules and a
        reconciliation runs both.
        """
        return self._post(
            f"/ontology-packs/{self.resolve_pack(pack)}/reset", None, force=force
        ) or {}

    def regenerate(
        self,
        pack: str,
        *,
        version: str,
        skos_turtle: str,
        files: list[dict[str, Any]] | None = None,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Rebuild a pack from a SKOS document and report what would change.

        **Reports by default**, for the same reason `reset` does. An empty
        `files` is a legitimate request: it asks what the *installed* half
        would do and nothing about disk.

        A term the new document no longer carries is reported as **deprecated,
        never deleted** — read the result rather than the status code.
        """
        return self._post(
            f"/ontology-packs/{self.resolve_pack(pack)}/regenerate",
            {
                "version": version,
                "skosTurtle": skos_turtle,
                "files": files or [],
                "apply": apply,
            },
        ) or {}

    def resolve_pack(self, pack: str) -> str:
        """The storage id of a pack, given the name a person uses.

        A pack has two identifiers: `packId` is what everyone calls it
        ("demo") and `id` is the UUID the routes take. Making a caller know
        that — and fetch the list to translate — is precisely the work an
        SDK exists to absorb. Passing a UUID straight through is honoured
        too, so this is a convenience and never a restriction.
        """
        if _looks_like_uuid(pack):
            return pack
        for row in self.packs():
            if isinstance(row, dict) and row.get("packId") == pack:
                return row.get("id") or pack
        from ..exceptions import NotFoundError

        raise NotFoundError(f"no ontology pack named {pack!r}", status=404)

    def terms(self, pack: str) -> list[dict[str, Any]]:
        """The vocabulary one ontology pack declares — classes and
        properties both, as the pack itself defines them.

        `pack` may be the name ("demo") or the UUID.
        """
        return rows(self._get(f"/ontology-packs/{self.resolve_pack(pack)}/terms"))

    def term_iris(self, pack: str) -> list[str]:
        """Every IRI the pack declares.

        **Deliberately not called `classes()`.** The endpoint returns a
        pack's declared vocabulary without saying which entries are
        classes and which are properties, so a `classes()` here could only
        guess from the name — and a method that quietly returns properties
        alongside classes is worse than no method, because the caller has
        no way to notice. When the API distinguishes them, this splits.
        """
        return [
            t.get("sourceIri") or ""
            for t in self.terms(pack)
            if isinstance(t, dict) and t.get("sourceIri")
        ]

    def class_(self, iri: str, *, pack: str) -> OntologyClass:
        """One declared term by IRI, from a pack.

        Named `class_` because `class` is a keyword — the trailing
        underscore is the standard Python convention for exactly this,
        and is preferred over inventing `klass` or `cls`.
        """
        match = next(
            (t for t in self.terms(pack) if isinstance(t, dict) and t.get("sourceIri") == iri),
            None,
        )
        if match is None:
            from ..exceptions import NotFoundError

            raise NotFoundError(f"{iri} is not declared by pack {pack!r}", status=404)
        return OntologyClass(self, iri, match)

    # ---- kept imports: an external ontology held for comparison ----------------

    def imports(self) -> list[dict[str, Any]]:
        """External ontologies kept for comparison against packs."""
        return rows(self._get("/ontology-imports"))

    def keep_import(self, **body: Any) -> dict[str, Any]:
        """Keep an external ontology document (`document=`, `fileName=`)."""
        return self._post("/ontology-imports", body) or {}

    def resolve_imports(self, **body: Any) -> dict[str, Any]:
        """What a document's `owl:imports` resolve to, before keeping it."""
        return self._post("/ontology-imports/resolve", body) or {}

    def remove_import(self, import_id: str) -> Any:
        """Remove a kept import."""
        return self._delete(f"/ontology-imports/{import_id}")

    def compare_import(self, import_id: str, pack: str) -> dict[str, Any]:
        """Compare a kept import against a pack: what matches, what conflicts."""
        return self._post(f"/ontology-imports/{import_id}/compare/{pack}", {}) or {}

    # ---- comparing and merging into a pack --------------------------------------

    def compare(self, pack: str, **body: Any) -> dict[str, Any]:
        """Compare a document (`document=`) against a pack's ontology."""
        return self._post(f"/ontology-packs/{pack}/compare", body) or {}

    def queue_conflicts(self, pack: str, **body: Any) -> dict[str, Any]:
        """Put a comparison's conflicts in the review queue."""
        return self._post(f"/ontology-packs/{pack}/conflicts/queue", body) or {}

    def merge(self, pack: str, **body: Any) -> dict[str, Any]:
        """Execute a decided merge (`document=`, `plan=`), writing a new pack
        version."""
        return self._post(f"/ontology-packs/{pack}/merge", body) or {}

    def import_glossary(self, pack: str, **body: Any) -> dict[str, Any]:
        """Import a term list (`document=`, `fileName=`) as proposals."""
        return self._post(f"/packs/{pack}/import/glossary", body) or {}

    # ---- a pack's axioms, questions, glossary and model ---------------------------

    def axiom_proposals(self, pack: str, **params: Any) -> list[dict[str, Any]]:
        """Structural axioms proposed for a pack, awaiting a decision."""
        return rows(self._get(f"/packs/{pack}/axiom-proposals", **params))

    def propose_axiom(self, pack: str, **body: Any) -> dict[str, Any]:
        """Propose an axiom (`axiom=`, with evidence) for a person to decide."""
        return self._post(f"/packs/{pack}/axiom-proposals", body) or {}

    def decide_axiom(self, pack: str, proposal_id: str, **body: Any) -> dict[str, Any]:
        """Approve or reject a proposed axiom."""
        return self._patch(f"/packs/{pack}/axiom-proposals/{proposal_id}", body) or {}

    def competency_coverage(self, pack: str) -> dict[str, Any]:
        """Run the pack's competency questions and report what each returned —
        an empty answer points at a missing term or axiom."""
        return self._get(f"/packs/{pack}/competency-coverage") or {}

    def pack_queries(self, pack: str) -> list[dict[str, Any]]:
        """The pack's declared queries — its competency questions."""
        return rows(self._get(f"/packs/{pack}/queries"))

    def definition_drift(self, pack: str) -> dict[str, Any]:
        """Definitions the pack's documents state differently from the
        approved terms."""
        return self._get(f"/packs/{pack}/definition-drift") or {}

    def apply_definition_drift(self, pack: str, **body: Any) -> dict[str, Any]:
        """Replace exactly those drifted definitions in the pack's documents."""
        return self._post(f"/packs/{pack}/definition-drift/apply", body) or {}

    def pack_glossary(self, pack: str) -> Any:
        """The pack's `glossary.ttl`."""
        return self._get(f"/packs/{pack}/glossary")

    def pack_axioms(self, pack: str) -> Any:
        """The pack's `axioms.ttl` — the structural axioms a person approved."""
        return self._get(f"/packs/{pack}/axioms")

    def pack_expectations(self, pack: str) -> Any:
        """The pack's `expectations.ttl` — the SHACL expectations it installs."""
        return self._get(f"/packs/{pack}/expectations")

    def write_pack_glossary(self, pack: str, **body: Any) -> dict[str, Any]:
        """Write the pack's `glossary.ttl`, refusing to drop terms unless forced."""
        return self._put(f"/packs/{pack}/glossary", body) or {}

    def suggest_owl_model(self, pack: str) -> dict[str, Any]:
        """What each approved term becomes in OWL, decided by evidence, by rule,
        or proposed for the residue."""
        return self._post(f"/packs/{pack}/suggest-owl-model", {}) or {}


def rows(payload: object) -> list[Any]:
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "classes", "packs"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


def _looks_like_uuid(value: str) -> bool:
    """Cheap shape test, not validation. Getting it wrong costs one extra
    lookup that then fails with a clear NotFound, never a wrong answer."""
    return len(value) == 36 and value.count("-") == 4


def _iris(raw: dict[str, Any], *keys: str) -> list[str]:
    """The first key that holds a list, normalised to IRI strings.

    The API is not uniform across every ontology endpoint yet; reading
    several spellings here means no caller writes that branch, and a
    response that settles on one of them later needs no change.
    """
    for key in keys:
        value = raw.get(key)
        if isinstance(value, list):
            return [v if isinstance(v, str) else (v.get("iri") or v.get("id") or "") for v in value]
    return []
