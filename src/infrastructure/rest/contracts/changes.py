"""Response contracts for the local changes this repository is holding.

A change row names the artifact it changes the way this repository addresses it. The enterprise id is
carried too, because it is what the change is *against* and what a reviewer sees — but it is not
something a client can open, so it is never the only identifier offered.
"""

from __future__ import annotations

from typing import Literal

from src.infrastructure.rest.contracts.wire_shape import Closed


class ChangeSummary(Closed):
    """One local change: what it changes, what it says, and where it stands."""

    #: The change's own id. What a caller names to discard it — two changes against one artifact are
    #: ordinary, so the artifact is not enough to identify one.
    artifact_id: str
    target_id: str
    target_name: str
    #: How this repository addresses the artifact. Null where it is read directly rather than
    #: through a reference, which is the admin deployment's shape.
    reference_id: str | None
    kind: Literal["entity", "document", "diagram"]
    changed_fields: list[str]
    state: Literal["draft", "submitted"]
    #: `stale` means the enterprise artifact has moved since this was written. Computed on read, so
    #: it is never a claim the file makes about the world.
    condition: Literal["current", "stale", "conflicting"]


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
