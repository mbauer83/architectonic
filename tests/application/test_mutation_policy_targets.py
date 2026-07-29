"""Write-target rules of the mutation authorization policy: canonical path
resolution across exact, child, ``..``, relative, symlink, and non-configured
spellings, per intent."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    DiscardWrite,
    MutationAllowed,
    MutationDenied,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
    SyncHealth,
)
from src.application.mutation_policy import authorize


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    engagement = tmp_path / "engagements" / "ENG-POL" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    (engagement / "model").mkdir(parents=True)
    (enterprise / "model").mkdir(parents=True)
    return engagement, enterprise


def _snapshot(roots: tuple[Path, Path], *, admin_mode: bool = False) -> AuthorizationSnapshot:
    engagement, enterprise = roots
    return AuthorizationSnapshot(
        engagement_root=engagement.resolve(),
        enterprise_root=enterprise.resolve(),
        admin_mode=admin_mode,
        read_only=False,
        gate_block=None,
        sync_health=SyncHealth(),
    )


def _decide(roots: tuple[Path, Path], request: MutationRequest, *, admin_mode: bool = False):
    return authorize(_snapshot(roots, admin_mode=admin_mode), request)


class TestEngagementAuthoringTargets:
    def test_exact_engagement_root_allowed(self, roots) -> None:
        engagement, _ = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(engagement)))
        assert isinstance(decision, MutationAllowed)

    def test_dotdot_spelling_of_engagement_root_allowed(self, roots) -> None:
        engagement, _ = roots
        spelled = engagement / "model" / ".."
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(spelled)))
        assert isinstance(decision, MutationAllowed)

    def test_relative_spelling_of_engagement_root_allowed(self, roots, monkeypatch: pytest.MonkeyPatch) -> None:
        engagement, _ = roots
        monkeypatch.chdir(engagement.parent)
        decision = _decide(
            roots, MutationRequest("engagement_authoring", RepositoryWrite(Path(engagement.name)))
        )
        assert isinstance(decision, MutationAllowed)

    def test_symlink_to_engagement_root_allowed(self, roots, tmp_path: Path) -> None:
        engagement, _ = roots
        link = tmp_path / "engagement-link"
        link.symlink_to(engagement)
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(link)))
        assert isinstance(decision, MutationAllowed)

    def test_child_of_engagement_root_denied(self, roots) -> None:
        engagement, _ = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(engagement / "model")))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_engagement_root"

    def test_parent_escape_denied(self, roots) -> None:
        engagement, _ = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(engagement / "..")))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_engagement_root"

    def test_enterprise_root_denied_as_forbidden(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(enterprise)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "enterprise_target_forbidden"

    def test_enterprise_child_denied_as_forbidden(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(enterprise / "model")))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "enterprise_target_forbidden"

    def test_symlink_to_enterprise_root_denied_as_forbidden(self, roots, tmp_path: Path) -> None:
        _, enterprise = roots
        link = tmp_path / "innocent-looking-link"
        link.symlink_to(enterprise)
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(link)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "enterprise_target_forbidden"

    def test_non_configured_root_denied(self, roots, tmp_path: Path) -> None:
        stray = tmp_path / "somewhere-else" / "architecture-repository"
        stray.mkdir(parents=True)
        decision = _decide(roots, MutationRequest("engagement_authoring", RepositoryWrite(stray)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_engagement_root"

    def test_admin_mode_does_not_open_enterprise_to_standard_authoring(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(
            roots, MutationRequest("engagement_authoring", RepositoryWrite(enterprise)), admin_mode=True
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "enterprise_target_forbidden"


class TestAdminAuthoringTargets:
    def test_enterprise_root_in_admin_mode_allowed(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(
            roots, MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise)), admin_mode=True
        )
        assert isinstance(decision, MutationAllowed)

    def test_without_admin_mode_denied(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(roots, MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "admin_mode_required"

    def test_engagement_root_denied_even_in_admin_mode(self, roots) -> None:
        engagement, _ = roots
        decision = _decide(
            roots, MutationRequest("enterprise_admin_authoring", RepositoryWrite(engagement)), admin_mode=True
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_enterprise_root"

    def test_enterprise_child_denied_even_in_admin_mode(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(
            roots,
            MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise / "model")),
            admin_mode=True,
        )
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_enterprise_root"


class TestPromotionTargets:
    def test_engagement_source_to_enterprise_destination_allowed(self, roots) -> None:
        engagement, enterprise = roots
        decision = _decide(roots, MutationRequest("promotion", PromotionWrite(engagement, enterprise)))
        assert isinstance(decision, MutationAllowed)

    def test_enterprise_source_denied(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(roots, MutationRequest("promotion", PromotionWrite(enterprise, enterprise)))
        assert isinstance(decision, MutationDenied)

    def test_engagement_destination_denied(self, roots) -> None:
        engagement, _ = roots
        decision = _decide(roots, MutationRequest("promotion", PromotionWrite(engagement, engagement)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_not_enterprise_root"


class TestWorkflowTargets:
    def test_save_submit_discard_accept_only_enterprise_root(self, roots) -> None:
        engagement, enterprise = roots
        for request in (
            MutationRequest("enterprise_save", RepositoryWrite(enterprise)),
            MutationRequest("enterprise_submit", RepositoryWrite(enterprise)),
            MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=False)),
            MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=True)),
        ):
            assert isinstance(_decide(roots, request), MutationAllowed), request
        for request in (
            MutationRequest("enterprise_save", RepositoryWrite(engagement)),
            MutationRequest("enterprise_submit", RepositoryWrite(engagement)),
            MutationRequest("enterprise_discard", DiscardWrite(engagement, pending_remote=False)),
        ):
            decision = _decide(roots, request)
            assert isinstance(decision, MutationDenied), request
            assert decision.code == "target_not_enterprise_root"


class TestTargetShapes:
    def test_intent_with_wrong_target_shape_denied(self, roots) -> None:
        engagement, enterprise = roots
        decision = _decide(roots, MutationRequest("engagement_authoring", PromotionWrite(engagement, enterprise)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_shape_mismatch"

    def test_discard_requires_discard_target_shape(self, roots) -> None:
        _, enterprise = roots
        decision = _decide(roots, MutationRequest("enterprise_discard", RepositoryWrite(enterprise)))
        assert isinstance(decision, MutationDenied)
        assert decision.code == "target_shape_mismatch"
