"""What else has to follow when an architecture artifact is renamed.

The rename itself rewrites every file in the repository that names the artifact. Other *tiers* may
also hold its id, and the write path must not reach into them: the confidential assurance store is
separately keyed, gated on being unlocked, and holds one-way references into architecture by design
(ADR@1783406789) — a write path that imported it would couple the open tier to the closed one and
would have to answer for a locked store.

So a follower registers itself instead, and the rename announces the fact. A follower reports what it
did in words the operator sees; one that cannot act — a locked store, an absent capability — reports
nothing and the rename proceeds. Registration is process-local and idempotent, in the same spirit as
the verifier's contribution registry.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: A follower answers with notes for the operator: what it retargeted, or nothing.
RenameFollower = Callable[["ArtifactRenamed"], tuple[str, ...]]

_FOLLOWERS: list[RenameFollower] = []


@dataclass(frozen=True)
class ArtifactRenamed:
    """An architecture artifact that has just been committed under a new id.

    Both ids share the `PREFIX@epoch.random` stem — a rename changes only the slug — so a follower
    matching on the stem finds references holding *any* older spelling, not just the one this rename
    started from.
    """

    old_artifact_id: str
    new_artifact_id: str


def register_rename_follower(follower: RenameFollower) -> None:
    """Register *follower*, once. Called by the composition root that owns the following tier."""
    if follower not in _FOLLOWERS:
        _FOLLOWERS.append(follower)


def registered_rename_followers() -> tuple[RenameFollower, ...]:
    return tuple(_FOLLOWERS)


def collect_follower_notes(
    followers: Iterable[RenameFollower], rename: ArtifactRenamed
) -> tuple[str, ...]:
    """Tell each of *followers*, and collect their notes.

    A follower that raises is not allowed to fail the rename: the rename is already committed, and a
    tier that could not keep up is a reconciliation problem, not a reason to refuse work that is done.
    The note says so, rather than the failure being silent.

    Takes its followers rather than reading the registry, so what to tell and whom to tell are
    separable: this part is a pure function of its arguments, and the registry is process state that
    only the composition root writes.
    """
    notes: list[str] = []
    for follower in followers:
        try:
            notes.extend(follower(rename))
        except Exception as exc:  # noqa: BLE001 - the rename is committed; report, never re-raise
            notes.append(f"A rename follower failed and its references may name the old slug: {exc}")
    return tuple(notes)


def announce_rename(rename: ArtifactRenamed) -> tuple[str, ...]:
    """Tell every registered follower about *rename*, and collect their notes."""
    return collect_follower_notes(registered_rename_followers(), rename)
