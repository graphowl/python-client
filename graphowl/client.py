"""The one client a developer constructs.

    from graphowl import GraphOWL

    owl = GraphOWL(url="https://api.graphowl.ai", api_key="...")
    owl.vocabulary.term("Invoice")

**Nine primitives, not 161 endpoints.** The server's route table is an
implementation detail; a client that exposes it makes every consumer learn
it and then hard-codes it into them. What a developer should have to know is
the difference between a vocabulary term, an ontology class and a graph
entity — which is real, and which this surface is shaped around.

Sub-clients are constructed on first access. There are nine of them, most
requests touch one, and building the other eight per client is work nobody
asked for. It also keeps `GraphOWL(...)` free of network calls, so
constructing one in a test costs nothing.
"""

from __future__ import annotations

from functools import cached_property

import httpx

from ._transport import Transport
from .resources.assets import Assets
from .resources.catalog import Catalog
from .resources.collaboration import Collaboration
from .resources.governance import Governance
from .resources.graph import Graph
from .resources.inference import Inference
from .resources.mapping import MappingResource
from .resources.modelling import Modelling
from .resources.ontology import Ontology
from .resources.ops import Ops
from .resources.query import Query, Semantic
from .resources.reconciliation import Reconciliation
from .resources.validation import Validation
from .resources.virtual_graphs import VirtualGraphs
from .resources.vocabulary import Vocabulary
from .resources.webhooks import Webhooks
from .resources.workspaces import Workspaces


class GraphOWL:
    def __init__(
        self,
        url: str = "http://localhost:8080",
        *,
        api_key: str | None = None,
        workspace: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        agent_service: str = "http://localhost:8899",
    ) -> None:
        """`transport` is for tests: pass an `httpx.MockTransport` and the
        whole SDK is exercisable with no server and no network."""
        self._transport = Transport(
            url,
            api_key,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
            workspace=workspace,
        )
        self._agent_service = agent_service

    @cached_property
    def vocabulary(self) -> Vocabulary:
        """What business terms mean."""
        return Vocabulary(self._transport)

    @cached_property
    def assets(self) -> Assets:
        """The catalogued things themselves — owners, versions, threads."""
        return Assets(self._transport)

    @cached_property
    def catalog(self) -> Catalog:
        """Tables, lineage, relationships, namespaces, custom properties."""
        return Catalog(self._transport)

    @cached_property
    def collaboration(self) -> Collaboration:
        """Threads, posts, announcements, inbox, memories."""
        return Collaboration(self._transport)

    @cached_property
    def webhooks(self) -> Webhooks:
        """Events in and events out."""
        return Webhooks(self._transport)

    @cached_property
    def workspaces(self) -> Workspaces:
        """Which customer's data a request is about.

        Not one of the nine primitives, and deliberately so: a workspace is
        not a kind of thing the graph holds, it is the boundary around which
        graph you are looking at. Reading it as a tenth primitive would put
        tenancy beside vocabulary and assets as though they answered the
        same sort of question.
        """
        return Workspaces(self._transport)

    @cached_property
    def ops(self) -> Ops:
        """Running the server: partitions, backups, streaming, telemetry."""
        return Ops(self._transport)

    @cached_property
    def ontology(self) -> Ontology:
        """What entity types exist, and how they relate."""
        return Ontology(self._transport)

    def graph(self, name: str | None = None) -> Graph:
        """One named graph. `owl.graph("demo")`.

        A method, not a property, because it takes a name — and the name
        is how the SDK stays free of any particular store: there is no
        driver to construct and no connection string to hold.
        """
        return Graph(self._transport, name)

    @cached_property
    def mapping(self) -> MappingResource:
        """How a source becomes canonical."""
        return MappingResource(self._transport)

    @cached_property
    def inference(self) -> Inference:
        """What can be derived, and why."""
        return Inference(self._transport)

    @cached_property
    def validation(self) -> Validation:
        """Whether it is valid."""
        return Validation(self._transport)

    @cached_property
    def reconciliation(self) -> Reconciliation:
        """Where two sides that should agree do not."""
        return Reconciliation(self._transport)

    @cached_property
    def governance(self) -> Governance:
        """Whether it is allowed."""
        return Governance(self._transport)

    @cached_property
    def query(self) -> Query:
        """Raw SPARQL and Cypher, for when you know the vocabulary."""
        return Query(self._transport)

    @cached_property
    def modelling(self) -> Modelling:
        """The model records, interviews, alignments and a source's own steps: one thin method per operation,
        generated from the contract (`tools/generate_modelling.py`)."""
        return Modelling(self._transport)

    @cached_property
    def virtual_graphs(self) -> VirtualGraphs:
        """Ask a source database in place, through a mapping a reviewer approved. Nothing is copied."""
        return VirtualGraphs(self._transport)

    @cached_property
    def semantic(self) -> Semantic:
        """Ask in words. Returns the answer *and* its trace."""
        return Semantic(self._transport, self._agent_service)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> GraphOWL:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
