"""GraphOWL — the developer-facing control plane.

    from graphowl import GraphOWL

    owl = GraphOWL(url="http://localhost:8080", api_key="...")
    owl.vocabulary.term("Invoice")

The surface is shaped around nine primitives rather than the route table, so a
caller asks "what is connected to what" instead of "which endpoint do I call".
"""

from .aio import AsyncGraphOWL
from .client import GraphOWL
from .exceptions import (
    AuthenticationError,
    GraphOWLError,
    NotFoundError,
    RateLimitError,
    RefusedError,
    ServerError,
    TransportError,
    ValidationError,
)
from .models import (
    Edge,
    Explanation,
    GraphSnapshot,
    InferenceResult,
    Node,
    ReasoningRun,
    Term,
    ValidationResult,
    ValidationRun,
    Violation,
)

__version__ = "0.1.0"

__all__ = [
    "AsyncGraphOWL",
    "AuthenticationError",
    "Edge",
    "Explanation",
    "GraphOWL",
    "GraphOWLError",
    "GraphSnapshot",
    "InferenceResult",
    "Node",
    "NotFoundError",
    "ReasoningRun",
    "RateLimitError",
    "RefusedError",
    "ServerError",
    "Term",
    "TransportError",
    "ValidationError",
    "ValidationResult",
    "ValidationRun",
    "Violation",
]
