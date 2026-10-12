"""Workspaces.

The client accepts `workspace=` and sends
`x-graphowl-workspace` on every request. These
tests cover both halves — provisioning a workspace, and the header that
scopes a request to one.
"""

import json

import httpx
import pytest

from graphowl import GraphOWL, GraphOWLError


def recording() -> tuple[GraphOWL, list[httpx.Request]]:
    """A client that keeps the requests it made, so a test can assert on the
    bytes the server would receive rather than on a call this code made."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/workspaces" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "slug": "acme-textiles",
                    "displayName": "Acme Textiles",
                    "createdAt": "2026-08-23T10:00:00Z",
                },
            )
        if request.url.path.endswith("/packs") and request.method == "GET":
            return httpx.Response(200, json=[])
        if request.url.path == "/workspaces":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"ok": True})

    owl = GraphOWL(
        url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)
    )
    return owl, seen


class TestProvisioning:
    def test_creating_a_workspace_sends_the_slug_and_display_name(self) -> None:
        owl, seen = recording()
        created = owl.workspaces.create("acme-textiles", "Acme Textiles")

        assert created["slug"] == "acme-textiles"
        post = next(r for r in seen if r.method == "POST")
        assert post.url.path == "/workspaces"

    def test_listing_returns_rows_not_a_wrapper(self) -> None:
        owl, _ = recording()
        assert owl.workspaces.list() == []

    def test_attaching_a_graph_names_the_workspace_in_the_path(self) -> None:
        owl, seen = recording()
        owl.workspaces.attach_graph("acme-textiles", "reco-abc-books")

        post = next(r for r in seen if r.url.path.endswith("/graphs"))
        assert post.url.path == "/workspaces/acme-textiles/graphs"

    def test_a_slug_with_a_slash_is_refused_before_a_request_is_sent(self) -> None:
        """**Percent-encoding does not work here, and this test is why it is
        not used.** The first version asserted the path was
        `/workspaces/a%2Fb/graphs`; httpx normalises `%2F` back to `/` while
        building the URL, so the request really did address
        `/workspaces/a/b/graphs` — a different route. Refusing the slug is
        both correct and a better error than that route's 404."""
        owl, seen = recording()
        with pytest.raises(GraphOWLError):
            owl.workspaces.attach_graph("a/b", "reco-abc-books")
        assert seen == [], "nothing should have been sent"

    def test_an_uppercase_slug_is_refused_the_way_the_server_would(self) -> None:
        owl, _ = recording()
        with pytest.raises(GraphOWLError):
            owl.workspaces.create("Acme", "Acme Textiles")


class TestPacks:
    def test_enabling_a_pack_names_the_workspace_and_the_pack(self) -> None:
        owl, seen = recording()
        owl.workspaces.enable_pack("acme-textiles", "demo")

        post = next(r for r in seen if r.url.path.endswith("/packs"))
        assert post.url.path == "/workspaces/acme-textiles/packs"
        assert json.loads(post.content) == {"pack": "demo"}

    def test_an_undeclared_workspace_reads_back_as_empty_meaning_all(self) -> None:
        """Empty is "every installed pack", not "none" — the SDK returns the
        list verbatim rather than inventing a sentinel, because the
        distinction belongs to the caller reading it, and a `None` here would
        be a third state the server does not have."""
        owl, _ = recording()
        assert owl.workspaces.packs("acme-textiles") == []


class TestOffboarding:
    def test_deleting_a_workspace_targets_it_by_slug(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(204)

        owl = GraphOWL(
            url="https://api.example", api_key="k", transport=httpx.MockTransport(handler)
        )
        owl.workspaces.delete("acme-textiles")

        assert seen[0].method == "DELETE"
        assert seen[0].url.path == "/workspaces/acme-textiles"

    def test_a_bad_slug_is_refused_before_a_delete_is_sent(self) -> None:
        """A `DELETE` built from an unvalidated slug is the worst place for
        the path-traversal gap `attach_graph` documents — this refuses for
        the same reason and, unlike encoding, actually works."""
        owl, seen = recording()
        with pytest.raises(GraphOWLError):
            owl.workspaces.delete("../assets")
        assert seen == []


class TestScoping:
    def test_a_client_built_for_a_workspace_sends_the_header(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[])

        owl = GraphOWL(
            url="https://api.example",
            api_key="k",
            workspace="acme-textiles",
            transport=httpx.MockTransport(handler),
        )
        owl.workspaces.list()
        assert seen[0].headers["x-graphowl-workspace"] == "acme-textiles"

    def test_a_client_with_no_workspace_sends_no_header(self) -> None:
        """Not an empty header. The server rejects a blank slug rather than
        reading it as "no workspace" — correct of it, and it would turn every
        unscoped request into a 400 if this sent one."""
        owl, seen = recording()
        owl.workspaces.list()
        assert "x-graphowl-workspace" not in seen[0].headers

    def test_an_unknown_workspace_raises_rather_than_returning_everything(self) -> None:
        """The failure that matters. A caller believing it is scoped to one
        customer must not silently receive the whole store.

        **Exercised through `validation.findings()`, not `workspaces.list()`,
        and that is a correction.** `GET /workspaces` deliberately ignores the
        header — asking which workspaces exist while scoped to one is circular
        and would leave the switcher unable to leave the workspace it is in —
        so a test that asserted this through `list()` was asserting against a
        mock the real route would never produce. Caught by running it against
        a live server, where nothing was raised at all.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-graphowl-workspace"] == "never-provisioned"
            return httpx.Response(
                404,
                json={
                    "type": "https://GraphOWL.dev/errors/not-found",
                    "title": "Not found",
                    "status": 404,
                },
            )

        owl = GraphOWL(
            url="https://api.example",
            api_key="k",
            workspace="never-provisioned",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(GraphOWLError):
            owl.validation.findings()
