"""Which customer's data a request is about.

**The client sends `x-graphowl-workspace` on every request when `workspace=` is set; a route reads it only where it is workspace-scoped.**
That is worth stating rather than quietly fixing: an SDK parameter that does
nothing is worse than an absent one, because a caller who sets it believes
they are scoped and is not.

Two things live here, and they are used by different people:

- **provisioning** (`create`, `attach_graph`) — administrative, run once per
  customer, usually by whatever system owns the customer list
- **scoping** — not a method at all. Pass `workspace=` to `GraphOWL(...)`
  and every request the client makes carries it, including the ones made by
  the other eight sub-clients. A per-call scope parameter was considered and
  rejected: there are well over a hundred methods, and a scope some of them
  forget is exactly the failure the header exists to prevent.
"""

from __future__ import annotations

import re
from typing import Any

from ._base import Resource, rows

#: What `the server` accepts. Duplicated here
#: rather than discovered by round trip, so a bad slug is refused before a
#: request is sent — the same discipline `graph.export` applies to its format
#: list.
_SLUG = re.compile(r"^[a-z0-9-]{1,64}$")


class Workspaces(Resource):
    def create(self, slug: str, display_name: str) -> dict[str, Any]:
        """Provision a workspace, or return the one already there.

        **Idempotent on `slug`, and answers `201` on a repeat rather than
        `409`.** The caller is usually a customer-creation path that has to
        survive a retry; a conflict would make the safe thing — repeating a
        timed-out create — look like an error.
        """
        _refuse_bad_slug(slug)
        return self._post("/workspaces", {"slug": slug, "displayName": display_name}) or {}

    def list(self) -> list[dict[str, Any]]:
        """Every provisioned workspace.

        Empty on a single-tenant deployment, which has no registry — that is
        a working state, not an error.
        """
        return rows(self._get("/workspaces"))

    def attach_graph(self, slug: str, graph: str) -> dict[str, Any]:
        """Record that an imported graph belongs to a workspace.

        Called **after** the import lands: the graph does not exist until
        then, and attaching a name that was never written puts an empty
        graph in the customer's scope — which reads as "uploaded, nothing
        found" rather than "not uploaded".

        **The slug is validated, not escaped, and that is a correction.**
        The obvious guard against a slug containing `/` is
        `quote(slug, safe="")` — and it does not work here: httpx
        normalises `%2F` back to `/` while building the URL, so
        `attach_graph("a/b", ...)` still addresses `/workspaces/a/b/graphs`.
        Measured, not assumed; a test asserting the encoded path failed
        against the decoded one. Refusing the slug outright is both correct
        and a better error than the 404 that path would produce.
        """
        _refuse_bad_slug(slug)
        return self._post(f"/workspaces/{slug}/graphs", {"graph": graph}) or {}

    def enable_pack(self, slug: str, pack: str) -> None:
        """Declare that a workspace uses an installed pack.

        **Enablement, not installation.** A pack is shared vocabulary and
        every customer of a tax deployment runs the same one; a private copy
        per customer would duplicate the ontology, the rules and the statute
        for no gain, and make "the rules changed" a per-customer migration.
        What varies is which packs a given customer's console is *about* — a
        hosted deployment serving several customers with different domains should not
        show one the other's vocabulary.
        """
        _refuse_bad_slug(slug)
        self._post(f"/workspaces/{slug}/packs", {"pack": pack})

    def disable_pack(self, slug: str, pack: str) -> None:
        """Stop showing a pack in a workspace. Its data and findings stay;
        the workspace simply no longer reads them."""
        _refuse_bad_slug(slug)
        self._delete(f"/workspaces/{slug}/packs/{pack}")

    def packs(self, slug: str) -> list[str]:
        """Which packs a workspace uses.

        **An empty list means every installed pack, not none.** Data
        isolation is the graph scope's job and fails closed; this narrows
        relevance, and reading absence as "no packs" would empty the console
        of every workspace that predates the declaration.
        """
        _refuse_bad_slug(slug)
        result = self._get(f"/workspaces/{slug}/packs")
        return list(result) if isinstance(result, list) else []

    def graphs(self, slug: str) -> list[str]:
        """The graphs attached to a workspace, sorted. A new workspace has
        none, and reads only what is attached — this list is its whole data
        boundary."""
        _refuse_bad_slug(slug)
        result = self._get(f"/workspaces/{slug}/graphs")
        return list(result) if isinstance(result, list) else []

    def delete(self, slug: str) -> None:
        """Offboard a customer — remove the workspace boundary.

        **The facts it pointed at stay.** `graph().delete_import(...)` is what
        removes those, and keeping the two apart means offboarding cannot
        destroy a customer's data by accident. Re-provisioning and
        re-attaching restores the customer whole.
        """
        _refuse_bad_slug(slug)
        self._delete(f"/workspaces/{slug}")


def _refuse_bad_slug(slug: str) -> None:
    """Refuse a slug the server would reject, before a request is sent.

    Uppercase is refused deliberately, matching the server: two slugs
    differing only by case would be two workspaces holding different
    customers, told apart by something nobody retyping one can see.
    """
    if not _SLUG.match(slug):
        from ..exceptions import ValidationError

        raise ValidationError(
            f"{slug!r} is not a workspace slug — lowercase letters, digits "
            "and '-', 1 to 64 characters"
        )
