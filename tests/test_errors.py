"""Every failure the SDK can surface is a typed GraphOWL error.

**A raw `httpx.HTTPStatusError` reaching a caller is a bug.** It leaks the
transport, it carries no `detail` a person can act on, and it forces every
consumer to write the same status-code switch the SDK should have written
once. GraphOWL already speaks RFC 9457 problem bodies
(`00d-api-conventions.md`), so the reason is always there to be kept —
dropping it is a choice, and the wrong one.
"""

import httpx
import pytest

from graphowl import (
    AuthenticationError,
    GraphOWL,
    GraphOWLError,
    NotFoundError,
    RateLimitError,
    RefusedError,
    TransportError,
    ValidationError,
)


def client(handler) -> GraphOWL:
    return GraphOWL(url="https://api.example", api_key="k", transport=httpx.MockTransport(handler))


def problem(status: int, title: str, detail: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"type": "https://GraphOWL.dev/errors/x", "title": title, "status": status, "detail": detail},
        headers={"content-type": "application/problem+json"},
    )


class TestStatusMapping:
    def test_401_is_an_authentication_error(self) -> None:
        c = client(lambda r: problem(401, "Token invalid", "the bearer token is invalid"))
        with pytest.raises(AuthenticationError):
            c.vocabulary.search("x")

    def test_403_is_a_refusal_not_an_authentication_failure(self) -> None:
        """A caller who *is* authenticated and lacks a capability must not
        be told to check their key — that sends them to the wrong fix."""
        c = client(lambda r: problem(403, "Refused", "requires the recordInvestigation capability"))
        with pytest.raises(RefusedError):
            c.vocabulary.search("x")

    def test_404_is_a_not_found_error(self) -> None:
        c = client(lambda r: problem(404, "Not found", "no such term"))
        with pytest.raises(NotFoundError):
            c.vocabulary.term("nope")

    def test_400_is_a_validation_error(self) -> None:
        c = client(lambda r: problem(400, "Validation failed", "`name` is required"))
        with pytest.raises(ValidationError):
            c.vocabulary.search("x")

    def test_422_is_also_a_validation_error(self) -> None:
        c = client(lambda r: problem(422, "Unprocessable", "bad shape"))
        with pytest.raises(ValidationError):
            c.vocabulary.search("x")

    def test_an_unmapped_status_is_still_a_graphowl_error(self) -> None:
        """A 418 must not escape as an httpx exception just because no
        specific class claims it."""
        c = client(lambda r: problem(418, "Teapot", "no"))
        with pytest.raises(GraphOWLError):
            c.vocabulary.search("x")

    def test_every_typed_error_is_a_graphowl_error(self) -> None:
        for cls in (AuthenticationError, NotFoundError, ValidationError, RefusedError, RateLimitError, TransportError):
            assert issubclass(cls, GraphOWLError)


class TestTheReasonSurvives:
    def test_the_problem_detail_is_the_message(self) -> None:
        c = client(lambda r: problem(400, "Validation failed", "`confidence` must be between 0 and 1"))
        with pytest.raises(ValidationError) as caught:
            c.vocabulary.search("x")
        assert "confidence" in str(caught.value)

    def test_the_status_and_title_are_kept_as_fields(self) -> None:
        c = client(lambda r: problem(404, "Not found", "no such term"))
        with pytest.raises(NotFoundError) as caught:
            c.vocabulary.term("nope")
        assert caught.value.status == 404
        assert caught.value.title == "Not found"

    def test_a_non_problem_body_still_produces_a_useful_message(self) -> None:
        """Not every failure comes from our own handlers — a proxy or a
        gateway returns HTML. The error must still say something."""
        c = client(lambda r: httpx.Response(502, text="<html>bad gateway</html>"))
        with pytest.raises(GraphOWLError) as caught:
            c.vocabulary.search("x")
        assert "502" in str(caught.value)

    def test_a_connection_failure_is_a_transport_error(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        c = client(refuse)
        with pytest.raises(TransportError):
            c.vocabulary.search("x")
