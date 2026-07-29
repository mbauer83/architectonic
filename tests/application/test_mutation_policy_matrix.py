"""Reason × action × mode matrix of the mutation authorization policy.

Every health reason is exercised against every enterprise workflow action (both
discard variants), engagement authoring, admin authoring, promotion, and
maintenance, under normal, admin, read-only, and transient-gate modes. A dirty
working tree never appears here: it is lifecycle state, not an authority input,
so ``enterprise_save`` stays authorized under remote faults regardless of tree
state — that invariant is what makes dirty-tree recovery possible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    DiscardWrite,
    GateBlock,
    MutationAllowed,
    MutationDenied,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
    SyncHealth,
    SyncHealthReason,
)
from src.application.mutation_policy import authorize, denied_intents

REMOTE_FAULTS: tuple[SyncHealthReason, ...] = ("fetch_failed", "upstream_missing", "diverged", "sync_state_unknown")
AGGREGATE_FAULTS: tuple[SyncHealthReason, ...] = ("state_file_corrupt", "repository_uninitialized")
ALL_REASONS: tuple[SyncHealthReason, ...] = REMOTE_FAULTS + AGGREGATE_FAULTS

ACTIONS = (
    "engagement_authoring",
    "enterprise_admin_authoring",
    "promotion",
    "enterprise_save",
    "enterprise_submit",
    "enterprise_discard_local",
    "enterprise_discard_pending",
    "maintenance",
)


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    engagement = tmp_path / "engagements" / "ENG-MTX" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    engagement.mkdir(parents=True)
    enterprise.mkdir(parents=True)
    return engagement.resolve(), enterprise.resolve()


def _request(action: str, roots: tuple[Path, Path]) -> MutationRequest:
    engagement, enterprise = roots
    match action:
        case "engagement_authoring":
            return MutationRequest("engagement_authoring", RepositoryWrite(engagement))
        case "enterprise_admin_authoring":
            return MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise))
        case "promotion":
            return MutationRequest("promotion", PromotionWrite(engagement, enterprise))
        case "enterprise_save":
            return MutationRequest("enterprise_save", RepositoryWrite(enterprise))
        case "enterprise_submit":
            return MutationRequest("enterprise_submit", RepositoryWrite(enterprise))
        case "enterprise_discard_local":
            return MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=False))
        case "enterprise_discard_pending":
            return MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=True))
        case "maintenance":
            return MutationRequest("maintenance", RepositoryWrite(enterprise))
    raise AssertionError(f"unknown action {action}")


def _snapshot(
    roots: tuple[Path, Path],
    *,
    admin_mode: bool = False,
    read_only: bool = False,
    gate_block: GateBlock | None = None,
    reason: SyncHealthReason | None = None,
) -> AuthorizationSnapshot:
    engagement, enterprise = roots
    return AuthorizationSnapshot(
        engagement_root=engagement,
        enterprise_root=enterprise,
        admin_mode=admin_mode,
        read_only=read_only,
        gate_block=gate_block,
        sync_health=SyncHealth(reason=reason, message="probe") if reason else SyncHealth(),
    )


def _allowed(snapshot: AuthorizationSnapshot, action: str, roots: tuple[Path, Path]) -> bool:
    return isinstance(authorize(snapshot, _request(action, roots)), MutationAllowed)


# Expected availability per (mode row): action → allowed?
_HEALTHY_NORMAL = {
    "engagement_authoring": True,
    "enterprise_admin_authoring": False,
    "promotion": True,
    "enterprise_save": True,
    "enterprise_submit": True,
    "enterprise_discard_local": True,
    "enterprise_discard_pending": True,
    "maintenance": True,
}
_HEALTHY_ADMIN = {**_HEALTHY_NORMAL, "enterprise_admin_authoring": True}
_READ_ONLY = {action: action == "maintenance" for action in ACTIONS}
_REMOTE_FAULT_NORMAL = {
    **_HEALTHY_NORMAL,
    "promotion": False,
    "enterprise_submit": False,
    "enterprise_discard_pending": False,
}
_AGGREGATE_FAULT_NORMAL = {
    **_HEALTHY_NORMAL,
    "promotion": False,
    "enterprise_save": False,
    "enterprise_submit": False,
    "enterprise_discard_local": False,
    "enterprise_discard_pending": False,
}


class TestHealthyModes:
    @pytest.mark.parametrize("action", ACTIONS)
    def test_normal_mode(self, roots, action: str) -> None:
        assert _allowed(_snapshot(roots), action, roots) is _HEALTHY_NORMAL[action]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_admin_mode(self, roots, action: str) -> None:
        assert _allowed(_snapshot(roots, admin_mode=True), action, roots) is _HEALTHY_ADMIN[action]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_read_only_denies_all_external_repository_intents(self, roots, action: str) -> None:
        assert _allowed(_snapshot(roots, read_only=True), action, roots) is _READ_ONLY[action]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_read_only_gate_block_equivalent(self, roots, action: str) -> None:
        assert _allowed(_snapshot(roots, gate_block="read_only"), action, roots) is _READ_ONLY[action]

    @pytest.mark.parametrize("action", ACTIONS)
    def test_transient_sync_gate_block_denies_all_but_maintenance(self, roots, action: str) -> None:
        assert _allowed(_snapshot(roots, gate_block="sync_in_progress"), action, roots) is _READ_ONLY[action]


class TestRemoteRelationshipFaults:
    @pytest.mark.parametrize("reason", REMOTE_FAULTS)
    @pytest.mark.parametrize("action", ACTIONS)
    def test_normal_mode_matrix(self, roots, reason: SyncHealthReason, action: str) -> None:
        assert _allowed(_snapshot(roots, reason=reason), action, roots) is _REMOTE_FAULT_NORMAL[action]

    @pytest.mark.parametrize("reason", REMOTE_FAULTS)
    def test_save_stays_available_for_dirty_tree_recovery(self, roots, reason: SyncHealthReason) -> None:
        """Working-tree dirtiness is not a policy input: under a persisted remote
        fault the local commit that resolves a dirty tree must stay authorized."""
        decision = authorize(_snapshot(roots, reason=reason), _request("enterprise_save", roots))
        assert isinstance(decision, MutationAllowed)

    @pytest.mark.parametrize("reason", REMOTE_FAULTS)
    def test_denials_carry_reason_and_code(self, roots, reason: SyncHealthReason) -> None:
        decision = authorize(_snapshot(roots, reason=reason), _request("enterprise_submit", roots))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "sync_health"
        assert decision.health_reason == reason

    @pytest.mark.parametrize("reason", REMOTE_FAULTS)
    @pytest.mark.parametrize("action", ACTIONS)
    def test_admin_mode_does_not_lift_health_denials(self, roots, reason: SyncHealthReason, action: str) -> None:
        expected = {**_REMOTE_FAULT_NORMAL, "enterprise_admin_authoring": True}
        assert _allowed(_snapshot(roots, admin_mode=True, reason=reason), action, roots) is expected[action]


class TestAggregateFaults:
    @pytest.mark.parametrize("reason", AGGREGATE_FAULTS)
    @pytest.mark.parametrize("action", ACTIONS)
    def test_normal_mode_matrix(self, roots, reason: SyncHealthReason, action: str) -> None:
        assert _allowed(_snapshot(roots, reason=reason), action, roots) is _AGGREGATE_FAULT_NORMAL[action]


class TestDeniedIntentsProjection:
    @pytest.mark.parametrize("reason", REMOTE_FAULTS)
    def test_remote_faults_deny_remote_affecting_intents_only(self, roots, reason: SyncHealthReason) -> None:
        _, enterprise = roots
        local = denied_intents(reason, DiscardWrite(enterprise, pending_remote=False))
        pending = denied_intents(reason, DiscardWrite(enterprise, pending_remote=True))
        assert local == frozenset({"promotion", "enterprise_submit"})
        assert pending == frozenset({"promotion", "enterprise_submit", "enterprise_discard"})

    @pytest.mark.parametrize("reason", AGGREGATE_FAULTS)
    def test_aggregate_faults_deny_every_workflow_intent(self, roots, reason: SyncHealthReason) -> None:
        _, enterprise = roots
        denied = denied_intents(reason, RepositoryWrite(enterprise))
        assert denied == frozenset(
            {"promotion", "enterprise_save", "enterprise_submit", "enterprise_discard"}
        )

    @pytest.mark.parametrize("reason", ALL_REASONS)
    def test_no_reason_ever_denies_engagement_or_maintenance(self, roots, reason: SyncHealthReason) -> None:
        _, enterprise = roots
        denied = denied_intents(reason, RepositoryWrite(enterprise))
        assert "engagement_authoring" not in denied
        assert "enterprise_admin_authoring" not in denied
        assert "maintenance" not in denied
