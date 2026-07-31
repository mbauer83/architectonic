"""Response contracts for the git-sync operations.

Four operations move work between the working tree, the engagement remote and the enterprise review
branch: save engagement, save enterprise, submit enterprise, withdraw enterprise. Each reports
something different — a commit, a branch, a discarded branch — and this module says which.

**Four contracts, not the one the manifest first named.** ``SyncOperationResponse`` was a placeholder
for a DTO nobody had written, and writing it as declared would have produced a model whose only
guaranteed field is ``ok``, with seven optionals covering four unrelated outcomes. A caller could not
tell from the type whether to read ``commit``, ``branch`` or ``discarded_branch``, which is the
"documents an object and promises nothing" problem in a thinner disguise — the exact thing the
response-contract work exists to remove. So the manifest's four rows now name four contracts. That is
a refinement of a Phase 0 placeholder rather than a change of direction: the plan itself prefers a
discriminated union for ``/completeness`` where the shapes genuinely differ, and they genuinely differ
here.

Every field below is one the handlers in ``routers/sync.py`` actually return;
``test_sync_operation_contracts.py`` holds each contract against its handler's returns.
"""

from __future__ import annotations

from src.infrastructure.gui.contracts.wire_nulls import NullsOmitted


class _SyncOutcome(NullsOmitted):
    """``ok`` is on every sync response, and it is the only thing all four share.

    The null-omitting policy is declared once here, for the whole surface, rather than on the one
    contract that currently has optional fields. Vacuous for the other three — a model with no
    optionals has nothing to omit — and it means a field added to any of them later inherits the
    surface's answer instead of raising the question again. The fitness function requires every route
    serving a marked DTO to declare ``response_model_exclude_none``, which is what keeps the claim and
    the routes from drifting apart.

    Retained even though a non-``ok`` outcome is an HTTP error rather than ``ok: false``: the GUI's
    sync surfaces branch on it, and removing it from the wire to tidy the model would be a breaking
    change made for the model's benefit rather than the caller's.
    """

    ok: bool


class EngagementSaveResponse(_SyncOutcome):
    """A commit on the engagement repository, optionally pushed.

    ``pushed`` echoes the request because the two outcomes are operationally different — a local
    commit is recoverable by the author alone, a pushed one is visible to everyone — and a caller that
    asked to push needs confirmation that it happened rather than an assumption that it did.
    """

    commit: str
    pushed: bool
    message: str


class EnterpriseSaveResponse(_SyncOutcome):
    """A commit on the enterprise working branch. No ``pushed``: enterprise work is published by
    ``submit``, which is a separate operation with its own review semantics."""

    commit: str
    message: str


class EnterpriseSubmitResponse(_SyncOutcome):
    """The review branch the enterprise work is now on.

    ``already_submitted`` distinguishes "I pushed it just now" from "it was already pending", which is
    why submitting twice is safe: the second call reports the existing branch and the time it was
    pushed rather than failing or creating a second one. Both are absent on a first submission, under
    the null-omitting policy, so their presence *is* the signal.
    """

    branch: str
    already_submitted: bool | None = None
    pushed_at: str | None = None


class EnterpriseWithdrawResponse(_SyncOutcome):
    """The branch whose pending changes were discarded.

    Named ``discarded_branch`` rather than ``branch`` because the two carry opposite news — one says
    where the work now lives, the other says what no longer exists — and a caller logging either
    should not have to know which operation it came from to read it correctly.
    """

    discarded_branch: str
