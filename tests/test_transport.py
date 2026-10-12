"""Retries, and the two ways they go wrong.

A retry that fires on the wrong status wastes the caller's time on a failure
that will never change. A retry that fires on the wrong *method* creates
things twice. The second is the dangerous one, and it is the one a test has
to pin because nothing about a duplicated POST looks like an error.
"""

import httpx
import pytest

from graphowl import (
    GraphOWL,
    GraphOWLError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
    ValidationError,
)


def recording(*responses):
    """A transport that replays `responses` and counts what it was asked."""
    calls: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.MockTransport(handler), calls


def client(transport, **kw) -> GraphOWL:
    owl = GraphOWL(url="https://api.example", api_key="k", transport=transport, **kw)
    # No real sleeping in tests: the delays are asserted separately.
    owl._transport._sleep = lambda _s: None
    return owl


class TestWhatIsRetried:
    def test_a_503_is_retried_and_can_succeed(self) -> None:
        t, calls = recording(httpx.Response(503), httpx.Response(200, json=[]))
        assert client(t).vocabulary.search("x") == []
        assert len(calls) == 2

    def test_a_429_is_retried(self) -> None:
        t, calls = recording(httpx.Response(429), httpx.Response(200, json=[]))
        client(t).vocabulary.search("x")
        assert len(calls) == 2

    def test_a_connection_failure_is_retried(self) -> None:
        t, calls = recording(httpx.ConnectError("down"), httpx.Response(200, json=[]))
        client(t).vocabulary.search("x")
        assert len(calls) == 2

    def test_retries_are_bounded_and_then_it_raises(self) -> None:
        t, calls = recording(httpx.Response(503))
        with pytest.raises(ServerError):
            client(t, max_retries=2).vocabulary.search("x")
        assert len(calls) == 3  # the first attempt plus two retries

    def test_max_retries_zero_means_one_attempt(self) -> None:
        t, calls = recording(httpx.Response(503))
        with pytest.raises(ServerError):
            client(t, max_retries=0).vocabulary.search("x")
        assert len(calls) == 1

    def test_a_connection_failure_is_bounded_by_the_same_count(self) -> None:
        """**A mutation test found this, not a read-through.** The 503 path had its bound
        pinned above; this one had only `is_retried`, so changing its
        guard from `<` to `<=` survived — one extra connection attempt per
        call, against a host that is already refusing them. Two branches
        implementing one policy need the boundary asserted on both."""
        t, calls = recording(httpx.ConnectError("down"))
        with pytest.raises(TransportError):
            client(t, max_retries=2).vocabulary.search("x")
        assert len(calls) == 3  # the first attempt plus two retries

    def test_a_connection_failure_with_no_retries_is_attempted_once(self) -> None:
        t, calls = recording(httpx.ConnectError("down"))
        with pytest.raises(TransportError):
            client(t, max_retries=0).vocabulary.search("x")
        assert len(calls) == 1


class TestWhatIsNotRetried:
    def test_a_400_is_not_retried(self) -> None:
        """It will be a 400 again. Retrying spends the budget and delays
        the error the caller needs to see."""
        t, calls = recording(httpx.Response(400, json={"detail": "bad"}))
        with pytest.raises(ValidationError):
            client(t).vocabulary.search("x")
        assert len(calls) == 1

    def test_a_404_is_not_retried(self) -> None:
        t, calls = recording(httpx.Response(404, json={"detail": "no"}))
        with pytest.raises(Exception):
            client(t).vocabulary.term("x")
        assert len(calls) == 1

    def test_a_post_is_never_retried(self) -> None:
        """**The one that would be silent.** A retried create that
        actually succeeded the first time makes two of the thing, and
        nothing in the response says so. Until the server offers an
        idempotency key, POST is not safe to repeat."""
        t, calls = recording(httpx.Response(503), httpx.Response(200, json={}))
        with pytest.raises(ServerError):
            client(t)._transport.request("POST", "/anything", json={})
        assert len(calls) == 1


class TestRetryAfter:
    def test_the_header_is_honoured_over_our_own_backoff(self) -> None:
        """A server that says 30 seconds means it. Backing off 0.25s three
        times just burns the retries before the window opens."""
        t, _ = recording(
            httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200, json=[])
        )
        owl = GraphOWL(url="https://api.example", api_key="k", transport=t)
        slept: list[float] = []
        owl._transport._sleep = slept.append
        owl.vocabulary.search("x")
        assert slept == [7.0]

    def test_a_garbage_retry_after_falls_back_to_backoff(self) -> None:
        t, _ = recording(
            httpx.Response(503, headers={"retry-after": "sometime"}), httpx.Response(200, json=[])
        )
        owl = GraphOWL(url="https://api.example", api_key="k", transport=t)
        slept: list[float] = []
        owl._transport._sleep = slept.append
        owl.vocabulary.search("x")
        assert slept and slept[0] > 0

    def test_backoff_grows_and_is_capped(self) -> None:
        from graphowl._transport import _backoff

        assert _backoff(1) < _backoff(2) < _backoff(3)
        assert _backoff(50) == 2.0

    def test_a_rate_limit_error_carries_retry_after(self) -> None:
        t, _ = recording(httpx.Response(429, headers={"retry-after": "12"}))
        with pytest.raises(RateLimitError) as caught:
            client(t).vocabulary.search("x")
        assert caught.value.retry_after == 12.0


class TestTransportBasics:
    def test_the_api_key_is_sent_as_a_bearer_token(self) -> None:
        t, calls = recording(httpx.Response(200, json=[]))
        client(t).vocabulary.search("x")
        assert calls[0].headers["authorization"] == "Bearer k"

    def test_no_api_key_sends_no_authorization_header(self) -> None:
        """A local dev server needs none, and sending `Bearer None` would
        be worse than sending nothing."""
        t, calls = recording(httpx.Response(200, json=[]))
        GraphOWL(url="https://api.example", transport=t).vocabulary.search("x")
        assert "authorization" not in calls[0].headers

    def test_a_workspace_is_sent_when_given(self) -> None:
        t, calls = recording(httpx.Response(200, json=[]))
        GraphOWL(url="https://api.example", workspace="production", transport=t).vocabulary.search("x")
        assert calls[0].headers["x-graphowl-workspace"] == "production"

    def test_an_empty_body_is_none_not_an_error(self) -> None:
        """204 on delete is normal, and calling .json() on it raises."""
        t, _ = recording(httpx.Response(204))
        assert client(t)._transport.request("DELETE", "/x") is None

    def test_constructing_a_client_makes_no_request(self) -> None:
        t, calls = recording(httpx.Response(200, json=[]))
        GraphOWL(url="https://api.example", transport=t)
        assert calls == []


class TestAnHtmlAnswerIsNotAnAnswer:
    """**A 200 carrying the console's HTML means the route does not exist.**

    This server answers an unrouted GET from the single-page app's
    fallback: status 200, `text/html`, the console. That is the exact
    shape that let six invented paths through a green unit suite once
    already, and the SDK's own report on it was
    `GraphOWLError: 200 response was not JSON` — which reads as a
    serialisation problem and sends the reader to look at the parser.

    Found live on `ops.bolt_status()`, whose route is behind
    `#[cfg(feature = "bolt")]` and genuinely absent from a default build.
    "This endpoint is not present on that server" is the true statement,
    and `NotFoundError` is where a caller already looks for it.
    """

    def _html(self) -> GraphOWL:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, text="<!doctype html><title>GraphOWL</title>",
                headers={"content-type": "text/html; charset=utf-8"},
            )

        return GraphOWL(url="https://api.example", api_key="k",
                        transport=httpx.MockTransport(handler))

    def test_html_where_json_was_expected_is_a_missing_route(self) -> None:
        with pytest.raises(NotFoundError) as caught:
            self._html().ops.bolt_status()
        assert "/admin/bolt/status" in str(caught.value)

    def test_it_says_the_route_is_absent_not_that_parsing_failed(self) -> None:
        with pytest.raises(NotFoundError) as caught:
            self._html().ops.bolt_status()
        assert "not JSON" not in str(caught.value)

    def test_a_non_html_body_that_will_not_parse_is_still_a_plain_error(self) -> None:
        """The narrow claim. Only `text/html` carries the "no such route"
        meaning; a truncated JSON body is a different failure and must not
        be relabelled into a 404 that never happened."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b'{"partial":',
                                  headers={"content-type": "application/json"})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        with pytest.raises(GraphOWLError) as caught:
            owl.ops.subscriptions()
        assert not isinstance(caught.value, NotFoundError)


class TestFieldErrorsSurviveTheMapping:
    """**"1 field failed validation" names no field.**

    This server's validation problems put the sentence a person can act on
    in RFC 9457's `errors` extension member, not in `detail`:

        {"detail": "1 field failed validation",
         "title": "Validation failed",
         "errors": [{"field": "sidecar", "code": "required",
                     "detail": "no whelk sidecar is configured for this
                                deployment"}]}

    The SDK read `detail` alone, so `inference.classify()` raised
    *"1 field failed validation"* — true, useless, and actively
    misleading: it points at the caller's arguments when the real answer
    is that this deployment has no EL reasoner attached. Found by running
    the same call with curl and reading a message the SDK had thrown away.
    """

    def _rejecting(self, body: dict) -> GraphOWL:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=body)

        return GraphOWL(url="https://api.example", api_key="k",
                        transport=httpx.MockTransport(handler))

    def test_the_field_and_its_reason_reach_the_message(self) -> None:
        owl = self._rejecting({
            "detail": "1 field failed validation",
            "title": "Validation failed",
            "errors": [{"field": "sidecar", "code": "required",
                        "detail": "no whelk sidecar is configured for this deployment"}],
        })
        with pytest.raises(ValidationError) as caught:
            owl.inference.classify()
        message = str(caught.value)
        assert "sidecar" in message
        assert "no whelk sidecar is configured for this deployment" in message

    def test_every_field_is_named_not_only_the_first(self) -> None:
        """A caller fixing one field at a time pays one round trip per
        field; the server already accumulates them, so dropping all but
        the first would discard work it deliberately did."""
        owl = self._rejecting({
            "detail": "2 fields failed validation",
            "errors": [{"field": "from", "detail": "required"},
                       {"field": "to", "detail": "required"}],
        })
        with pytest.raises(ValidationError) as caught:
            owl.inference.classify()
        assert "from" in str(caught.value)
        assert "to" in str(caught.value)

    def test_the_structured_errors_are_reachable_not_only_readable(self) -> None:
        """The string is for a human. A caller mapping a rejection back
        onto its own form fields needs the list."""
        owl = self._rejecting({
            "detail": "1 field failed validation",
            "errors": [{"field": "seed", "code": "type", "detail": "not a namespace code"}],
        })
        with pytest.raises(ValidationError) as caught:
            owl.inference.classify()
        assert caught.value.errors == [
            {"field": "seed", "code": "type", "detail": "not a namespace code"}
        ]

    def test_a_problem_with_no_errors_member_is_unchanged(self) -> None:
        owl = self._rejecting({"detail": "plain rejection", "title": "Nope"})
        with pytest.raises(ValidationError) as caught:
            owl.inference.classify()
        assert str(caught.value) == "plain rejection"
        assert caught.value.errors == []


class TestIdempotentPushes:
    """**The SDK said the server had no idempotency key. It has an
    idempotency key.**

    `_transport.py` carried this, beside the retry set:

        The server offers no idempotency key yet; when it does, POST can
        join this set.

    `POST /ingest` reads `Idempotency-Key` and has three documented
    outcomes — replay the original response, `409` on the same key with
    different content, `409` while the first is still in flight. The
    server's own handler calls it "mandatory for push, not optional — at
    least-once transport duplicates without it, and a pusher that times
    out has no way to know whether the first attempt landed".

    The SDK could not send one at all: `Transport.request` had no way to
    pass a header. So the one endpoint built to make a push safely
    retryable was, through this client, the one that could not be retried.

    **POST joins the retry set only when a key was sent.** Making POST
    retryable outright would be wrong — most of them create something and
    do not honour a key. The condition the old comment named is exactly
    the right one; it was just never implemented.
    """

    def test_a_key_is_sent_when_asked_for(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        owl.mapping.ingest(items=[{"fullyQualifiedName": "a"}], idempotency_key="abc-123")
        assert seen[0].headers["idempotency-key"] == "abc-123"

    def test_a_key_is_derived_from_the_body_when_none_is_given(self) -> None:
        """**Derived, not random.** A random key makes every retry a new
        request, which is the behaviour the key exists to prevent. The same
        push twice is the same key, so the second is a replay rather than a
        duplicate."""
        keys: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            keys.append(request.headers.get("idempotency-key", ""))
            return httpx.Response(200, json={})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        owl.mapping.ingest(items=[{"fullyQualifiedName": "a"}])
        owl.mapping.ingest(items=[{"fullyQualifiedName": "a"}])
        owl.mapping.ingest(items=[{"fullyQualifiedName": "b"}])
        assert keys[0] and keys[0] == keys[1], "same content must be the same key"
        assert keys[2] != keys[0], "different content must be a different key"

    def test_a_caller_can_opt_out(self) -> None:
        """Explicit `None` sends nothing — there are pushes where a caller
        genuinely wants two identical writes to be two writes."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        owl = GraphOWL(url="https://api.example", api_key="k",
                       transport=httpx.MockTransport(handler))
        owl.mapping.ingest(items=[], idempotency_key=None)
        assert "idempotency-key" not in seen[0].headers

    def test_a_keyed_push_is_retried_where_a_plain_post_is_not(self) -> None:
        t, calls = recording(httpx.Response(503), httpx.Response(200, json={}))
        client(t).mapping.ingest(items=[{"fullyQualifiedName": "a"}])
        assert len(calls) == 2, "a keyed push is safe to retry"

    def test_a_push_that_opted_out_is_still_never_retried(self) -> None:
        t, calls = recording(httpx.Response(503))
        with pytest.raises(ServerError):
            client(t).mapping.ingest(items=[], idempotency_key=None)
        assert len(calls) == 1

    def test_an_ordinary_post_is_still_never_retried(self) -> None:
        """The blast radius. Nothing else may become retryable by accident."""
        t, calls = recording(httpx.Response(503))
        with pytest.raises(ServerError):
            client(t).validation.run()
        assert len(calls) == 1
