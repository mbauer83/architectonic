"""Promotion failure path on the enterprise working branch: an abort is a git reset
to a pre-promotion checkpoint (accumulated unsaved work protected by the checkpoint
commit), never a file-restore loop — and engagement-side GAR replacement failing can
no longer roll back a verified enterprise write, which previously could lose the
artifact on BOTH sides (enterprise copies reverted while engagement originals were
already unlinked)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion
from src.infrastructure.write.artifact_write.promote_transaction import GitWorktreeTransaction
from tests.support.git_workflow_fixtures import (
    ENG_ENTITY_ID,
    build_workflow_pair,
    git,
    write_entity,
)


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    return build_workflow_pair(tmp_path)


def _porcelain(repo: Path) -> str:
    return git(repo, "status", "--porcelain")


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


class TestGitWorktreeTransaction:
    def test_abort_restores_exact_pre_state_including_unsaved_prior_work(self, pair) -> None:
        _, enterprise = pair
        prior = write_entity(enterprise, "REQ@1000000801.PriorW.prior-unsaved-work", "Prior Unsaved Work")
        pre_status, pre_head = _porcelain(enterprise), _head(enterprise)

        tx = GitWorktreeTransaction(enterprise)
        tx.begin()
        junk = enterprise / "model" / "motivation" / "requirement" / "half-copied-promotion-file.md"
        junk.write_text("partial promotion residue", encoding="utf-8")
        (enterprise / "docs" / "standard").mkdir(parents=True)
        tx.abort()

        assert prior.exists()
        assert not junk.exists()
        assert not (enterprise / "docs").exists()
        assert _porcelain(enterprise) == pre_status  # prior work is unsaved again, nothing else
        assert _head(enterprise) == pre_head

    def test_commit_keeps_prior_and_new_work_unsaved(self, pair) -> None:
        _, enterprise = pair
        prior = write_entity(enterprise, "REQ@1000000802.PriorX.prior-unsaved-work-two", "Prior Two")
        pre_head = _head(enterprise)

        tx = GitWorktreeTransaction(enterprise)
        tx.begin()
        promoted = write_entity(enterprise, "REQ@1000000803.NewPrm.newly-promoted", "Newly Promoted")
        tx.commit()

        assert prior.exists() and promoted.exists()
        assert _head(enterprise) == pre_head  # checkpoint released; save lifecycle owns commits
        status = _porcelain(enterprise)
        assert "PriorX" in status and "NewPrm" in status

    def test_abort_before_begin_is_an_error_not_a_silent_noop(self, pair) -> None:
        _, enterprise = pair
        with pytest.raises(RuntimeError):
            GitWorktreeTransaction(enterprise).abort()


def _plan_for_entity(engagement: Path, enterprise: Path):
    index = combined_artifact_index(engagement, enterprise)
    registry = ArtifactRegistry(index)
    repo = ArtifactRepository(index)
    plan = plan_promotion(
        None, registry, repo,
        entity_ids=[ENG_ENTITY_ID],
        engagement_root=engagement, enterprise_root=enterprise,
    )
    return plan, registry


class TestExecuteFailurePaths:
    def test_verification_failure_resets_the_branch_and_leaves_engagement_untouched(
        self, pair, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engagement, enterprise = pair
        pre_status, pre_head = _porcelain(enterprise), _head(enterprise)
        plan, registry = _plan_for_entity(engagement, enterprise)
        monkeypatch.setattr(
            "src.infrastructure.write.artifact_write.promote_execute.collect_verification_errors",
            lambda *_a, **_k: ["E999: forced post-copy failure"],
        )

        result = execute_promotion(
            plan, engagement, enterprise, registry, transaction=GitWorktreeTransaction(enterprise)
        )

        assert result.executed is False and result.rolled_back is True
        assert _porcelain(enterprise) == pre_status
        assert _head(enterprise) == pre_head
        source = engagement / "model" / "motivation" / "requirement" / f"{ENG_ENTITY_ID}.md"
        assert source.exists()  # no GAR replacement ran

    def test_verification_failure_rollback_spares_unsaved_prior_work(
        self, pair, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engagement, enterprise = pair
        prior = write_entity(enterprise, "REQ@1000000804.PriorY.accumulated-promotion", "Accumulated")
        plan, registry = _plan_for_entity(engagement, enterprise)
        monkeypatch.setattr(
            "src.infrastructure.write.artifact_write.promote_execute.collect_verification_errors",
            lambda *_a, **_k: ["E999: forced post-copy failure"],
        )

        result = execute_promotion(
            plan, engagement, enterprise, registry, transaction=GitWorktreeTransaction(enterprise)
        )

        assert result.rolled_back is True
        assert prior.exists()
        assert prior.read_text(encoding="utf-8").startswith("---")
        promoted = enterprise / "model" / "motivation" / "requirement" / f"{ENG_ENTITY_ID}.md"
        assert not promoted.exists()

    def test_exception_mid_copy_aborts_without_partial_state(
        self, pair, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engagement, enterprise = pair
        pre_status, pre_head = _porcelain(enterprise), _head(enterprise)
        plan, registry = _plan_for_entity(engagement, enterprise)
        monkeypatch.setattr(
            "src.infrastructure.write.artifact_write.promote_execute.apply_viewpoint_resolutions",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("forced mid-execution crash")),
        )

        result = execute_promotion(
            plan, engagement, enterprise, registry, transaction=GitWorktreeTransaction(enterprise)
        )

        assert result.executed is False and result.rolled_back is True
        assert any("forced mid-execution crash" in e for e in result.verification_errors)
        assert _porcelain(enterprise) == pre_status
        assert _head(enterprise) == pre_head

    def test_gar_replacement_failure_never_rolls_back_the_verified_enterprise_write(
        self, pair, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engagement, enterprise = pair
        plan, registry = _plan_for_entity(engagement, enterprise)
        monkeypatch.setattr(
            "src.infrastructure.write.artifact_write.promote_execute._replace_promoted_with_gars",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("forced GAR failure")),
        )

        result = execute_promotion(
            plan, engagement, enterprise, registry, transaction=GitWorktreeTransaction(enterprise)
        )

        assert result.executed is True and result.rolled_back is False
        promoted = enterprise / "model" / "motivation" / "requirement" / f"{ENG_ENTITY_ID}.md"
        source = engagement / "model" / "motivation" / "requirement" / f"{ENG_ENTITY_ID}.md"
        # The artifact exists on BOTH sides — never on neither.
        assert promoted.exists() and source.exists()
        assert any("GAR" in w and "forced GAR failure" in w for w in result.plan.warnings)
