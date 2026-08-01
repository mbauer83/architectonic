"""Response contracts for the platform surface: server identity, repository sync state, id allocation.

What a client asks about the *installation* rather than the model — which roots are served, whether
writing is permitted, whether the enterprise repository is in step with its remote. None of it names an
artifact, which is why it sits apart from the entity and diagram contracts.

Every field here is derived from its producer, and the optionals mean something specific in each case:
a repository that is not configured is ``null`` rather than an empty object, because "not part of this
installation" and "configured and clean" are different answers to the same question.
"""

from __future__ import annotations

from src.application.mutation_authorization import SyncHealthReason
from src.infrastructure.git.enterprise_sync_state import EnterpriseSyncStatus
from src.infrastructure.rest.contracts.wire_shape import Closed
from src.infrastructure.rest.routers._sync_authority import BlockKind


class ServerInfoResponse(Closed):
    """Which roots this backend serves, and whether it will accept writes.

    The two roots are ``null`` when the installation has no such repository — distinct from an empty
    string, which would read as "configured, at the filesystem root".
    """

    admin_mode: bool
    read_only: bool
    engagement_root: str | None
    enterprise_root: str | None


class AllocatedIdentifierResponse(Closed):
    """A freshly minted workspace-scoped id for a diagram-owned entity.

    One field, and deliberately an object rather than a bare string: an allocation may later need to
    report the prefix it resolved or the generation it was minted against, and a top-level scalar cannot
    grow either without breaking every caller.
    """

    id: str


class SyncHealthResponse(Closed):
    """Why the enterprise sync is unhealthy, when it is.

    The reason is the domain's own closed vocabulary rather than a string, so a client can branch on it
    — and neither the message nor the timestamp is optional: the producer's ``SyncHealth`` declares both
    as required, and publishing them as nullable would invite a null check for a case that cannot occur.
    """

    reason: SyncHealthReason
    message: str
    observed_at: str


class EngagementSyncStateResponse(Closed):
    """The engagement repository's state — local-only, so uncommitted work is all there is to report."""

    has_uncommitted_changes: bool


class EnterpriseSyncStateResponse(Closed):
    """The enterprise repository's state against its remote.

    ``commits_ahead`` is absent rather than zero when the repository is not accumulating: the count is
    only meaningful in that mode, and a zero would claim it had been measured.
    """

    #: The lifecycle vocabulary the sync state itself declares, not a free string.
    status: EnterpriseSyncStatus
    #: The reader-facing wording for ``status``, composed server-side so every surface says it the same.
    label: str
    branch: str | None
    branch_tip: str | None
    pushed_at: str | None
    commits_behind: int | None
    has_uncommitted_changes: bool
    health: SyncHealthResponse | None
    commits_ahead: int | None = None


class DeniedIntentResponse(Closed):
    """Whether one sync intent is currently refused, and under which code."""

    denied: bool
    code: str | None


class SyncAuthorityResponse(Closed):
    """What the current authority state permits, per intent.

    ``denied_intents`` is keyed by intent name — an open map because the intents are declared by the
    mutation-authorization layer, and mirroring that vocabulary here would put it in two places.
    """

    #: Which kind of block is in force, if any — ``"none"`` when writing is permitted. Never null: the
    #: projection always answers, and ``"none"`` is that answer.
    block_kind: BlockKind
    blocked_reason: SyncHealthReason | None
    blocked_message: str | None
    denied_intents: dict[str, DeniedIntentResponse]


class SyncStatusResponse(Closed):
    """Both repositories' sync state, and what the authority currently permits.

    Each repository is ``null`` when it is not configured, which is why neither is merged into the
    envelope: a flat shape could not distinguish "no enterprise repository" from "clean".
    """

    engagement: EngagementSyncStateResponse | None
    enterprise: EnterpriseSyncStateResponse | None
    authority: SyncAuthorityResponse
