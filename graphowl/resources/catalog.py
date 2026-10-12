"""Tables, lineage, relationships, namespaces and custom properties.

The structural metadata around an asset: what it is made of, where its
values came from, and what a workspace has chosen to record beyond the
built-in fields.

Kept apart from `assets` because these are *relations between* catalogued
things rather than the things themselves — and because lineage in
particular is a graph of its own, with its own upstream and downstream
questions.
"""

from __future__ import annotations

from typing import Any

from ._base import Resource, rows


class Catalog(Resource):
    # ---- tables ---------------------------------------------------------

    def tables(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/tables", **params))

    def table(self, table_id: str) -> dict[str, Any]:
        return self._get(f"/tables/{table_id}") or {}

    def create_table(self, **body: Any) -> dict[str, Any]:
        return self._post("/tables", body) or {}

    def update_table(self, table_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/tables/{table_id}", changes) or {}

    def delete_table(self, table_id: str) -> None:
        self._delete(f"/tables/{table_id}")

    def table_relationships(self, table_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/tables/{table_id}/relationships"))

    def relate_tables(self, table_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/tables/{table_id}/relationships", body) or {}

    def delete_relationship(self, relationship_id: str) -> None:
        self._delete(f"/relationships/{relationship_id}")

    # ---- lineage --------------------------------------------------------

    def lineage(self, asset_id: str, **params: Any) -> dict[str, Any]:
        """Where an asset's values came from, and what depends on them."""
        return self._get(f"/lineage/asset/{asset_id}", **params) or {}

    def add_lineage(self, **body: Any) -> dict[str, Any]:
        """Assert that one asset derives from another."""
        return self._post("/lineage", body) or {}

    def delete_lineage(self, edge_id: str) -> None:
        self._delete(f"/lineage/{edge_id}")

    # ---- extension points ------------------------------------------------

    def custom_properties(self) -> list[dict[str, Any]]:
        """Fields a workspace has added beyond the built-in ones."""
        return rows(self._get("/custom-properties"))

    def add_custom_property(self, **body: Any) -> dict[str, Any]:
        return self._post("/custom-properties", body) or {}

    def update_custom_property(self, property_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/custom-properties/{property_id}", changes) or {}

    def delete_custom_property(self, property_id: str) -> None:
        self._delete(f"/custom-properties/{property_id}")

    def namespaces(self) -> list[dict[str, Any]]:
        """Registered IRI prefixes.

        Worth knowing about: the agents' single most common query failure
        is an undeclared prefix, and this is where the declared ones live.
        """
        return rows(self._get("/namespaces"))

    def add_namespace(self, **body: Any) -> dict[str, Any]:
        return self._post("/namespaces", body) or {}

    # ---- domains ------------------------------------------------------------
    #
    # A domain is the *organisational* home of an asset — "Finance", "Supply
    # Chain" — as opposed to its ontological type. The two are routinely
    # conflated and are not the same question: a `demo:Invoice` belongs to
    # Finance, and knowing its class tells you nothing about who owns it.

    def domains(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/domains", **params))

    def domain(self, domain_id: str) -> dict[str, Any]:
        return self._get(f"/domains/{domain_id}") or {}

    def create_domain(self, **body: Any) -> dict[str, Any]:
        return self._post("/domains", body) or {}

    def update_domain(self, domain_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/domains/{domain_id}", changes) or {}

    def delete_domain(self, domain_id: str) -> dict[str, Any]:
        """Answers 200 with a body, not 204 — it reports what it detached."""
        return self._delete(f"/domains/{domain_id}") or {}

    def domain_children(self, domain_id: str) -> list[dict[str, Any]]:
        """Sub-domains. Domains nest so ownership can sit at the level
        somebody actually operates at."""
        return rows(self._get(f"/domains/{domain_id}/children"))

    def domain_asset_count(self, domain_id: str) -> dict[str, Any]:
        """How many assets this domain holds, without listing them."""
        return self._get(f"/domains/{domain_id}/assets/count") or {}

    # ---- data contracts ------------------------------------------------------
    #
    # What a producer promises about an asset — freshness, schema, volume — and
    # whether it is currently keeping that promise.

    def contracts(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/contracts", **params))

    def contract(self, contract_id: str) -> dict[str, Any]:
        return self._get(f"/contracts/{contract_id}") or {}

    def create_contract(self, **body: Any) -> dict[str, Any]:
        return self._post("/contracts", body) or {}

    def contract_slas(self, contract_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/contracts/{contract_id}/slas"))

    def set_contract_status(self, contract_id: str, **body: Any) -> dict[str, Any]:
        return self._post(f"/contracts/{contract_id}/status", body) or {}

    def clear_contract_breaches(self, contract_id: str) -> dict[str, Any]:
        """Clear recorded breaches. Returns what it cleared.

        A breach is a historical fact, so this reports rather than silently
        discards — "the contract is green now" and "somebody cleared the
        record" are different states and a reader needs to tell them apart.
        """
        return self._delete(f"/contracts/{contract_id}/breaches") or {}

    # ---- data products -------------------------------------------------------
    #
    # A curated bundle of assets published as one thing. Distinct from a
    # domain: a domain is who owns an asset, a product is what it is packaged
    # into for consumers.

    def data_products(self, **params: Any) -> list[dict[str, Any]]:
        return rows(self._get("/data-products", **params))

    def data_product(self, product_id: str) -> dict[str, Any]:
        return self._get(f"/data-products/{product_id}") or {}

    def create_data_product(self, **body: Any) -> dict[str, Any]:
        return self._post("/data-products", body) or {}

    def update_data_product(self, product_id: str, **changes: Any) -> dict[str, Any]:
        return self._patch(f"/data-products/{product_id}", changes) or {}

    def delete_data_product(self, product_id: str) -> None:
        self._delete(f"/data-products/{product_id}")

    def data_product_assets(self, product_id: str) -> list[dict[str, Any]]:
        return rows(self._get(f"/data-products/{product_id}/assets"))

    def add_product_asset(self, product_id: str, asset_id: str) -> Any:
        """A PUT: adding an asset that is already a member is the state the
        caller asked for, so it must not be an error."""
        return self._put(f"/data-products/{product_id}/assets/{asset_id}")

    def remove_product_asset(self, product_id: str, asset_id: str) -> None:
        self._delete(f"/data-products/{product_id}/assets/{asset_id}")

    # ---- usage ---------------------------------------------------------------
    #
    # **This lives here rather than under `analytics.usage*`.**
    # There is already `graph().analytics()` (whole-graph structure) and
    # `assets.analytics()` (one asset's neighbourhood), and a third thing
    # called analytics meaning "who queried what" would make the word useless.
    # Usage is a fact about catalogued assets, so it sits with the catalogue.

    def usage(self, fqn: str, **params: Any) -> dict[str, Any]:
        """How often this asset is read: query counts and a trend.

        Per-asset because that is what the API offers, and because a
        whole-estate usage dump is an unbounded query the SDK should not
        make look cheap.

        **A summary object, not a list of reads** — it was declared
        `list[dict]` and therefore answered `[]`, which reads as "nobody
        queried this", for a response carrying four fields of evidence.
        `usage_rollups()` is the one that really is a list.
        """
        return self._get(f"/usage/{fqn}", **params) or {}

    def record_usage(self, **body: Any) -> dict[str, Any]:
        return self._post("/usage", body) or {}

    def usage_rollups(self, fqn: str, **params: Any) -> list[dict[str, Any]]:
        """Usage aggregated over time, rather than every raw read."""
        return rows(self._get(f"/usage/{fqn}/rollups", **params))

    def prune_usage(self, **body: Any) -> dict[str, Any]:
        """Drop usage rows past their retention window."""
        return self._post("/usage/prune", body) or {}

    # ---- column lineage and predicates ---------------------------------------

    def column_lineage(self, edge_id: str) -> list[dict[str, Any]]:
        """Lineage at column granularity, hung off one lineage edge.

        The level a person actually debugs at: "which upstream column
        produced this wrong total" is unanswerable from table lineage.
        """
        return rows(self._get(f"/lineage/{edge_id}/columns"))

    def set_column_lineage(self, edge_id: str, columns: Any) -> Any:
        """Replace an edge's column mapping.

        A PUT: a column mapping is a complete statement about how one
        asset derives from another, and adding a pair without saying what
        else holds is how two systems end up disagreeing about it.
        """
        return self._put(f"/lineage/{edge_id}/columns", columns)

    def reconcile_lineage(self, **body: Any) -> dict[str, Any]:
        """Re-derive lineage from the current sources and report the drift."""
        return self._post("/lineage/reconcile", body) or {}

    def add_predicate(self, **body: Any) -> dict[str, Any]:
        """Register a relationship type.

        Write-only here: there is no listing endpoint. The predicates in
        use are visible through the graph itself.
        """
        return self._post("/predicates", body) or {}

    # ---- the whole picture ------------------------------------------------

    def overview(self) -> dict[str, Any]:
        """The counts the console's front page shows — assets,
        relationships, ontology classes, open contradictions."""
        return self._get("/overview") or {}

    def search(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Search across assets, glossary terms and metrics at once."""
        return rows(self._get("/search", q=query, **params))
