"""Canonical route policy for the local changes this repository is holding.

A change is a local edit to an artifact the engagement does not own, awaiting review upstream. It is
addressed by its own id here — not by the artifact it changes — because two changes against one
artifact are ordinary and a caller discarding one must be able to say which.

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
)
