"""The eighth mutation intent: proposing a change to a promoted artifact from a non-admin deployment.

Repository mutations are authorised by a closed intent paired with a typed target, matched
exhaustively. None of the seven existing members fits this activity, and the two shortest ways to
pretend otherwise are both wrong:

* Widen `PromotionWrite` so one target means two things. It would pass every policy test there is,
  because those assert that the intents behave — not that a wrong one is refused.
* Require `admin_mode`. That deletes the reason the feature exists: an admin deployment can already
  edit enterprise content directly through the admin operations.

**Only the remote-touching half of the workflow carries it.** Drafting a proposal, revising one and
withdrawing a draft write the engagement repository and nothing else, so they take
`engagement_authoring` and stay available through a fetch failure — the same reason the existing
policy keeps local commits available as the recovery path. Submitting, rebasing and withdrawing an
already-pushed proposal touch the remote, so they take this intent and are denied with `promotion`
and `enterprise_submit`.

**Withdrawal after submission is why the target names two roots.** It must mark the proposal
terminal in the engagement repository *and* delete the pushed branch from the enterprise one. One
authorisation over one root cannot cover both, and two requests invite the losing order: mark it
terminal (allowed under a remote fault), then fail to delete the branch (denied) — leaving a live
review branch that nothing observes, because the proposal is terminal and the branch is the
reviewer's.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    MutationAllowed,
    MutationDenied,
    MutationIntent,
    MutationRequest,
    PromotionWrite,
    ProposalWrite,
    RepositoryWrite,
    SyncHealth,
    SyncHealthReason,
)
from src.application.mutation_policy import authorize, denied_intents
from src.infrastructure.rest.routers.sync._authority import WORKFLOW_ACTIONS, _request_for

_REMOTE_FAULTS: tuple[SyncHealthReason, ...] = (
    "fetch_failed", "upstream_missing", "diverged", "sync_state_unknown",
)


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    engagement = tmp_path / "engagements" / "ENG-P" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    engagement.mkdir(parents=True)
    enterprise.mkdir(parents=True)
    return engagement, enterprise


def _snapshot(roots: tuple[Path, Path], **overrides: object) -> AuthorizationSnapshot:
    engagement, enterprise = roots
    fields: dict[str, object] = {
        "engagement_root": engagement.resolve(),
        "enterprise_root": enterprise.resolve(),
        "admin_mode": False,
        "read_only": False,
        "gate_block": None,
        "sync_health": SyncHealth(reason=None, message=""),
    }
    return AuthorizationSnapshot(**{**fields, **overrides})  # type: ignore[arg-type]


class TestTheVocabularyStaysExhaustive:
    """Adding a ninth intent must reach the surface that reports it, not only the policy."""

    def test_every_intent_is_reachable_through_a_workflow_action(self, roots) -> None:
        snapshot = _snapshot(roots)
        reachable = {
            request.intent
            for action in WORKFLOW_ACTIONS
            if (request := _request_for(action, snapshot)) is not None
        }
        assert reachable == set(get_args(MutationIntent)), (
            "an intent exists that no workflow action asks about, so the authority surface can "
            "never report it blocked:\n"
            f"  unreachable: {sorted(set(get_args(MutationIntent)) - reachable)}"
        )

    def test_the_proposal_intent_is_the_eighth(self) -> None:
        assert "enterprise_proposal" in get_args(MutationIntent)
        assert len(get_args(MutationIntent)) == 8


class TestTheTargetShapeIsItsOwn:
    def test_the_proposal_intent_refuses_a_promotion_target(self, roots) -> None:
        """The widening this exists to prevent, asserted rather than left to a docstring."""
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots),
            MutationRequest("enterprise_proposal", PromotionWrite(engagement, enterprise)),
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_shape_mismatch"

    def test_promotion_refuses_a_proposal_target(self, roots) -> None:
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots),
            MutationRequest("promotion", ProposalWrite(engagement, enterprise)),
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_shape_mismatch"

    def test_it_authorises_the_engagement_record_and_the_enterprise_branch(self, roots) -> None:
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots), MutationRequest("enterprise_proposal", ProposalWrite(engagement, enterprise))
        )
        assert isinstance(decision, MutationAllowed), decision

    def test_the_roots_are_not_interchangeable(self, roots) -> None:
        """Swapping them would write the proposal's state into the repository it is proposing about."""
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots), MutationRequest("enterprise_proposal", ProposalWrite(enterprise, engagement))
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "enterprise_target_forbidden"


class TestItNeedsNoAdminMode:
    """The precondition the whole feature rests on: a non-admin deployment can propose."""

    def test_a_non_admin_deployment_may_propose(self, roots) -> None:
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots, admin_mode=False),
            MutationRequest("enterprise_proposal", ProposalWrite(engagement, enterprise)),
        )
        assert isinstance(decision, MutationAllowed), decision

    def test_direct_enterprise_authoring_still_requires_it(self, roots) -> None:
        """The contrast that makes the point: the existing intent for enterprise writes does."""
        _, enterprise = roots
        decision = authorize(
            _snapshot(roots, admin_mode=False),
            MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise)),
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "admin_mode_required"


class TestOnlyTheRemoteTouchingHalfIsDenied:
    @pytest.mark.parametrize("reason", _REMOTE_FAULTS)
    def test_a_remote_fault_denies_the_proposal_intent(self, reason: SyncHealthReason, roots) -> None:
        engagement, enterprise = roots
        assert "enterprise_proposal" in denied_intents(reason, ProposalWrite(engagement, enterprise))

    @pytest.mark.parametrize("reason", _REMOTE_FAULTS)
    def test_a_remote_fault_never_denies_drafting(self, reason: SyncHealthReason, roots) -> None:
        """Drafting is `engagement_authoring`, which is never denied — the recovery path stays open."""
        engagement, _ = roots
        assert "engagement_authoring" not in denied_intents(reason, RepositoryWrite(engagement))

    @pytest.mark.parametrize("reason", ("state_file_corrupt", "repository_uninitialized"))
    def test_an_unusable_aggregate_denies_it_too(self, reason: SyncHealthReason, roots) -> None:
        engagement, enterprise = roots
        assert "enterprise_proposal" in denied_intents(reason, ProposalWrite(engagement, enterprise))

    @pytest.mark.parametrize("reason", _REMOTE_FAULTS)
    def test_the_denial_reaches_a_real_decision(self, reason: SyncHealthReason, roots) -> None:
        """`denied_intents` is consulted by `authorize`; asserting the set alone would not show that."""
        engagement, enterprise = roots
        decision = authorize(
            _snapshot(roots, sync_health=SyncHealth(reason=reason, message="no remote")),
            MutationRequest("enterprise_proposal", ProposalWrite(engagement, enterprise)),
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "sync_health"
        assert decision.health_reason == reason
