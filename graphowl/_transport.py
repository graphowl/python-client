"""The one place HTTP happens.

Every resource calls `Transport.request`; nothing else in the SDK knows what
a status code is. That is what makes the typed-error contract in
`exceptions.py` enforceable rather than aspirational — there is exactly one
function to get right.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

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

#: Statuses worth trying again. 429 and 5xx are transient by definition;
#: nothing else is — a 400 retried is a 400 twice, and a 404 retried is a
#: slower 404.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Methods safe to retry by the verb alone. **POST is absent on purpose**:
#: it is the only verb here that can create something, and a retried create
#: that actually succeeded the first time makes two.
#:
#: A POST *carrying an idempotency key* is retried anyway — see
#: `Transport.request`'s `idempotent` flag. This comment used to end "the
#: server offers no idempotency key yet; when it does, POST can join this
#: set", which was wrong once `POST /ingest` existed:
#: the key existed, the SDK simply had no way to send a header.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})


class Transport:
    def __init__(
        self,
        url: str,
        api_key: str | None,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        workspace: str | None = None,
    ) -> None:
        headers = {"accept": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        if workspace:
            headers["x-graphowl-workspace"] = workspace
        self._client = httpx.Client(
            base_url=url.rstrip("/"), headers=headers, timeout=timeout, transport=transport
        )
        self._max_retries = max_retries
        self._sleep = time.sleep

    def request(
        self,
        method: str,
        path: str,
        *,
        decode: bool = True,
        idempotent: bool = False,
        **kw: Any,
    ) -> Any:
        """`decode=False` hands back the body as the server typed it.

        Used by exports, which are mostly *not* JSON: n-djson, GraphML,
        Cypher script and a zstd archive all come back over this path, and
        parsing them as JSON turned a successful export into an exception.

        `idempotent=True` says this particular request may be retried even
        though its verb says otherwise — set by callers that send an
        idempotency key, because that is exactly what the key buys. It is
        per-request rather than per-route on purpose: the same POST is safe
        with a key and unsafe without one, so the route cannot decide.
        """
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, **kw)
            except httpx.HTTPError as exc:
                # A connection that never landed is retryable for the same
                # reason a 503 is: nothing happened, so nothing can be
                # duplicated by trying again.
                if attempt < self._max_retries and (
                    idempotent or method.upper() in IDEMPOTENT_METHODS
                ):
                    attempt += 1
                    self._sleep(_backoff(attempt))
                    continue
                raise TransportError(str(exc)) from exc

            if response.status_code in RETRY_STATUSES and attempt < self._max_retries:
                if idempotent or method.upper() in IDEMPOTENT_METHODS:
                    attempt += 1
                    self._sleep(_retry_delay(response, attempt))
                    continue

            if response.status_code >= 400:
                raise _error_for(response)
            if not response.content:
                return None
            content_type = response.headers.get("content-type", "")
            if not decode:
                # Bytes when it cannot be text in any encoding, text
                # otherwise. `application/zstd` decoded as UTF-8 is a
                # corrupted archive that only fails when somebody opens it.
                return (
                    response.json()
                    if content_type.startswith("application/json")
                    else response.content
                    if _is_binary(content_type)
                    else response.text
                )
            try:
                return response.json()
            except ValueError as exc:
                # **HTML here means the route does not exist.** The server
                # answers an unrouted GET from the console's single-page
                # fallback — status 200, `text/html` — so a JSON call that
                # comes back as a web page was never handled by anything.
                # Reporting that as a parse failure sends the reader to the
                # deserialiser; it is a missing endpoint, and this is the
                # shape that once let six invented paths past a green suite.
                #
                # Narrow on purpose: only `text/html` carries that meaning.
                # A truncated JSON body is a different fault and keeps the
                # plain error, rather than being relabelled a 404 the server
                # never sent.
                if "text/html" in response.headers.get("content-type", ""):
                    raise NotFoundError(
                        f"{method.upper()} {path} is not a route on this server "
                        f"— it answered with the console, which is what an "
                        f"unrouted path returns",
                        status=response.status_code,
                    ) from exc
                raise GraphOWLError(
                    f"{response.status_code} response was not JSON", status=response.status_code
                ) from exc

    def close(self) -> None:
        self._client.close()


#: Content types whose bytes are not text in any encoding. Everything else
#: an export produces (n-djson, XML, Cypher script, turtle) is text.
_BINARY_TYPES = ("application/zstd", "application/octet-stream", "application/zip", "application/gzip")


def _is_binary(content_type: str) -> bool:
    return content_type.split(";")[0].strip() in _BINARY_TYPES


def _backoff(attempt: int) -> float:
    """Exponential, capped. No jitter here: the cap is small and the retry
    count is 2, so the thundering-herd case this would smooth does not
    arise. Revisit if `max_retries` grows."""
    return min(0.25 * (2 ** (attempt - 1)), 2.0)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """`Retry-After` when the server said, our own backoff otherwise.

    Honouring the header is the difference between backing off and
    guessing — a server that says 30 seconds means it, and retrying at
    0.5s three times just spends the budget before the window opens.
    """
    header = response.headers.get("retry-after")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    return _backoff(attempt)


def _field_summary(error: dict[str, object]) -> str:
    """`field: reason`, and just the reason when no field was named —
    every field is rendered, not only the first, because the server
    accumulates them deliberately so a caller fixes them in one pass."""
    field = error.get("field")
    reason = error.get("detail") or error.get("code") or ""
    return f"{field}: {reason}" if field else str(reason)


def _error_for(response: httpx.Response) -> GraphOWLError:
    """Map one failed response onto its typed error, reason intact."""
    status = response.status_code
    detail = f"{status} {response.reason_phrase}".strip()
    title = None
    type_ = None
    try:
        body = response.json()
    except ValueError:
        body = None
    field_errors: list[dict[str, object]] = []
    if isinstance(body, dict):
        title = body.get("title")
        type_ = body.get("type")
        # `detail` is where RFC 9457 puts the sentence a person reads.
        # Falling back through `title` then the status line means the
        # message is never empty, whatever answered.
        detail = body.get("detail") or body.get("title") or detail
        # **And `errors` is where this server puts the sentence a person
        # can act on.** A validation problem's `detail` is a count — "1
        # field failed validation" — while the reason lives per field. The
        # SDK reported the count alone, so `inference.classify()` raised
        # "1 field failed validation" when the real answer was "no whelk
        # sidecar is configured for this deployment": a message pointing at
        # the caller's arguments for a deployment-shaped problem.
        raw = body.get("errors")
        if isinstance(raw, list):
            field_errors = [item for item in raw if isinstance(item, dict)]
        if field_errors:
            detail = f"{detail} ({'; '.join(_field_summary(f) for f in field_errors)})"

    if status == 401:
        return AuthenticationError(detail, status=status, title=title, type_=type_, errors=field_errors)
    if status == 403:
        return RefusedError(detail, status=status, title=title, type_=type_, errors=field_errors)
    if status == 404:
        return NotFoundError(detail, status=status, title=title, type_=type_, errors=field_errors)
    if status in (400, 422):
        return ValidationError(detail, status=status, title=title, type_=type_, errors=field_errors)
    if status == 429:
        after = response.headers.get("retry-after")
        return RateLimitError(
            detail,
            retry_after=float(after) if after and after.replace(".", "", 1).isdigit() else None,
            status=status,
            title=title,
            type_=type_,
            errors=field_errors,
        )
    if status >= 500:
        return ServerError(detail, status=status, title=title, type_=type_, errors=field_errors)
    return GraphOWLError(detail, status=status, title=title, type_=type_, errors=field_errors)
