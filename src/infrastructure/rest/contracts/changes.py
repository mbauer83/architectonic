"""Response contracts for the local changes this repository is holding.

A change row names the promoted artifact: its id and what it is called. Not the local reference
standing for it — that is machinery, excluded from every list and every search, and a row publishing
one invited a client to link it. The artifact a reader knows is the promoted one, which is what
search returns and what they edited.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_shape import Closed


class FieldDivergence(Closed):
    """One field of a stale change: what it asks for, and what the artifact says now.

    Both null where the value has no single line to show — a properties table, an attribute-type
    map. Naming the field as diverging is still worth saying; rendering a structured value here
    would be a second, worse spelling of what the artifact view already draws.
    """

    field: str
    proposed: str | None
    current: str | None


class ChangeSummary(Closed):
    """One local change: what it changes, what it says, and where it stands."""

    #: The change's own id. What a caller names to discard it — two changes against one artifact are
    #: ordinary, so the artifact is not enough to identify one.
    artifact_id: str
    target_id: str
    target_name: str
    kind: Literal["entity", "document", "diagram"]
    changed_fields: list[str]
    state: Literal["draft", "submitted"]
    #: `stale` means the enterprise artifact has moved since this was written. Computed on read, so
    #: it is never a claim the file makes about the world.
    condition: Literal["current", "stale", "conflicting"]
    #: What the change asks for beside what the artifact says now. Empty unless the change is
    #: stale: on a current one the two agree, and a value shown beside itself is noise.
    divergence: list[FieldDivergence]


class ChangeListResponse(Closed):
    """Every live change, ordered by the artifact each one changes."""

    changes: list[ChangeSummary]
    total: int


class ChangeDiscardedResponse(Closed):
    """What a discard did.

    The record is kept and moved to a terminal state rather than deleted: a change that was submitted
    has been seen by someone, and its disappearance would be indistinguishable from it never having
    existed. `discarded` is false when the change was already terminal, which is not an error.
    """

    artifact_id: str
    discarded: bool
    state: Literal["abandoned"]


class RebasedChange(Closed):
    """Where one change stood when the rebase rehearsed it, and what was done about it.

    `outcome` is `change_rebase`'s own vocabulary, and `reason` is what an author reads — for a
    conflict it is the verifier's refusal verbatim, because a second wording of a refusal is a
    second vocabulary for the same thing.
    """

    artifact_id: str
    target_id: str
    outcome: Literal["clean", "superseded", "conflicting"]
    reason: str
    #: Whether the change now records the revision it was just proven against. True only for a clean
    #: outcome, and only where the artifact's current revision could be read.
    restamped: bool


class ChangeRebasedResponse(Closed):
    """What the rehearsal concluded. Nothing is written for a superseded or conflicting change."""

    changes: list[RebasedChange]
    summary: str
