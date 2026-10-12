"""The canonical shapes the SDK returns.

**One graph representation, shared by every consumer.** The console's Explore
canvas, the agent pipeline and any future application all need to know
whether an edge was asserted or derived; if each defines its own node type
they will disagree about it, and the one that disagrees quietly is the one
that ships a wrong answer.

`inferred` is therefore not optional and not a detail. A derived fact
rendered identically to an asserted one is the single most misleading thing
a graph tool can do.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    type: str | None = None
    label: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    #: Derived by the reasoner rather than stated by a source.
    inferred: bool = False


class Edge(BaseModel):
    id: str | None = None
    source: str
    predicate: str
    target: str
    inferred: bool = False


class GraphSnapshot(BaseModel):
    """A bounded piece of the graph, ready to render or walk.

    **Bounded, and it says so.** `truncated` is how a caller learns the walk
    hit its limit rather than reaching the edge of the data — the difference
    between "this subject connects to nothing else" and "we stopped
    looking", which look identical without it.
    """

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    truncated: bool = False

    def node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    @property
    def inferred_edges(self) -> list[Edge]:
        return [e for e in self.edges if e.inferred]


class Path(BaseModel):
    """One route between two subjects. `nodes` includes both ends, so a
    direct edge is `length: 1` with two nodes."""

    length: int
    nodes: list[str] = Field(default_factory=list)


class PathSet(BaseModel):
    """Every route found, shortest first — and whether the search finished.

    **`truncated` is the point**, the same way it is on `GraphSnapshot`.
    Enumerating routes between two nodes in a dense graph is exponential,
    so the server stops; an empty `paths` with `truncated: true` means "we
    ran out of budget", which is not the same claim as "these two are not
    connected" and must never render as one.
    """

    paths: list[Path] = Field(default_factory=list)
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.paths)

    def __iter__(self) -> Any:  # type: ignore[override]
        return iter(self.paths)

    def __bool__(self) -> bool:
        """**False only when nothing was found *and* the search finished.**
        A truncated empty result is not an honest "no", so it does not get
        to look like one in an `if`."""
        return bool(self.paths) or self.truncated


class Term(BaseModel):
    """A business term. What a word *means*, not what type it is."""

    name: str
    definition: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    id: str | None = None


class Violation(BaseModel):
    focus_node: str
    path: str | None = None
    message: str
    severity: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    violations: list[Violation] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.valid:
            return "valid"
        return f"{len(self.violations)} violation(s)"


class Explanation(BaseModel):
    """Why a derived fact holds: the rule, and what it stood on.

    An inference the SDK cannot explain is a bug in the SDK, not an
    acceptable result — the engine returns derivations, so dropping them
    would be the client choosing to know less than the server told it.
    """

    fact: str
    rule: str | None = None
    premises: list[str] = Field(default_factory=list)


class ReasoningRun(BaseModel):
    """What one reasoner run did.

    Counts, because that is what the endpoint returns. A model that
    claimed to carry the derived facts would cost a hidden second request
    and would disagree with the server as soon as a run was large.

    `partial` and `capped` are the honest half: a run that hit its budget
    derived *some* of what follows, and a caller who reads `derived` alone
    would take an incomplete closure for a complete one.
    """

    derived: int = 0
    replaced: int = 0
    iterations: int = 0
    duration_ms: int = Field(0, alias="durationMs")
    technique: str | None = None
    partial: bool = False
    capped: int | None = None
    ignored_axioms: list[Any] = Field(default_factory=list, alias="ignoredAxioms")
    maintained_to: int | None = Field(None, alias="maintainedTo")

    model_config = {"populate_by_name": True}


class ValidationRun(BaseModel):
    """What one validation run found, as the endpoint reports it.

    `violations` here is a **count**. The violations themselves come from
    `validation.report()`, which pages them — mapping a count onto a list
    field would be a silently empty list on every run that found something.
    """

    conforms: bool = True
    violations: int = 0
    warnings: int = 0
    info: int = 0
    shapes: int = 0
    refused_shapes: int = Field(0, alias="refusedShapes")
    sparql_truncated: bool = Field(False, alias="sparqlTruncated")

    model_config = {"populate_by_name": True}


class InferenceResult(BaseModel):
    inferred_nodes: list[Node] = Field(default_factory=list)
    inferred_edges: list[Edge] = Field(default_factory=list)
    explanations: list[Explanation] = Field(default_factory=list)

    def explain(self, fact: str) -> Explanation | None:
        return next((e for e in self.explanations if e.fact == fact), None)
