"""Canonical route policy for the local changes this repository is holding.

A change is a local edit to an artifact the engagement does not own, awaiting review upstream. It is
addressed by its own id here — not by the artifact it changes — because two changes against one
artifact are ordinary and a caller discarding one must be able to say which.

Rebasing is the remedy for the state a change spends most of its life in. The enterprise branch
moves while changes wait, so staleness is not an edge case — and a product that could only report it
left an author with no move except to redo the work.

Discarding is a ``DELETE`` that keeps the record: the change moves to a terminal state rather than
vanishing, because a change that was submitted has been seen by someone and its disappearance would
be indistinguishable from it never having existed. So the response says what happened rather than
answering 204 — the resource is still there, and it no longer changes anything.
"""

from __future__ import annotations

from src.infrastructure.rest.route_policy._types import TYPED, RouteRow

_CHANGE = ("artifact_id",)

CHANGE_ROWS: tuple[RouteRow, ...] = (
    RouteRow(
        "GET", "/api/changes", "collection", "changes_list_changes", TYPED,
        cache_directive="no-cache",
    ),
    RouteRow(
        "DELETE", "/api/changes/{artifact_id}", "detail", "changes_discard_change",
        TYPED, identity_parameters=_CHANGE, mutation_domain="repository",
    ),
    RouteRow(
        # An action segment, not a `PATCH`: rebasing is not a field update. It re-applies the change
        # to the artifact as it stands and records what it was proven against, which is a thing done
        # to a change rather than a change to it.
        "POST", "/api/changes/{artifact_id}/rebase", "subresource", "changes_rebase_change",
        TYPED, identity_parameters=_CHANGE, mutation_domain="repository",
    ),
)
