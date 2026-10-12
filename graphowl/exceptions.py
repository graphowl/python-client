"""Every failure the SDK surfaces, as a typed error.

**A raw `httpx.HTTPStatusError` reaching a caller is a bug.** It leaks the
transport into code that asked about a graph, it carries no reason a person
can act on, and it makes every consumer write the same status-code switch
the SDK should write once.

GraphOWL answers failures with RFC 9457 problem bodies
(`00d-api-conventions.md`), so the reason is always there. Keeping it is the
whole job: `403` with "requires the recordInvestigation capability" tells a
caller to ask for a grant, while a bare `403` tells them to check their key
— which is the wrong fix, confidently given.
"""

from __future__ import annotations


class GraphOWLError(Exception):
    """Base class. Catching this catches everything the SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.title = title
        self.type = type_
        #: RFC 9457's `errors` extension member, verbatim. The message
        #: renders these for a human; a caller mapping a rejection back
        #: onto its own form fields needs the structure.
        self.errors = errors or []


class TransportError(GraphOWLError):
    """The request never reached a server, or its answer never arrived."""


class AuthenticationError(GraphOWLError):
    """401 — the credential is missing, malformed or rejected."""


class RefusedError(GraphOWLError):
    """403 — authenticated, and not allowed to do this.

    Deliberately distinct from `AuthenticationError`. A caller who holds a
    valid key and lacks a capability needs a grant, not a new key, and
    conflating the two sends them to the wrong fix.
    """


class NotFoundError(GraphOWLError):
    """404 — no such thing."""


class ValidationError(GraphOWLError):
    """400 or 422 — the request was understood and is not acceptable."""


class RateLimitError(GraphOWLError):
    """429 — too many requests. Carries `retry_after` when the server said."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]
        self.retry_after = retry_after


class ServerError(GraphOWLError):
    """5xx — the server failed. Retried automatically before you see this."""
