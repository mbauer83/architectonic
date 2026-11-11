"""Recording a repository's own work: staging it, committing it under the right identity, pushing it.

Both tiers are here on purpose. The engagement and enterprise commits differ only in which paths they
stage and which message they carry, and splitting them by tier would put one copy of the
stage-commit-report sequence on each side of the boundary — which is what the exclude-pathspec below
exists to prevent going wrong twice.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config.git_identity import optional_git_author
from src.infrastructure.git._git_command import (
    PUSH_TIMEOUT,
    STAGE_ALL_BUT_RUNTIME_STATE,
    commit_with_identity,
    run_repo_git,
)
from src.infrastructure.git.git_repository_state import current_commit, has_uncommitted_changes

logger = logging.getLogger(__name__)




def commit_enterprise_work(
    enterprise_root: Path,
    message: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> str:
    """Stage and commit all changes in the enterprise repo. Returns the new commit hash.

    Verifies the whole working tree first (it may hold manually edited files);
    a failing tree rejects the save with no commit and no state change.
    """
    from src.infrastructure.write.save_commit_verification import assert_repository_verifies  # noqa: PLC0415

    author = optional_git_author(author_name, author_email)
    if not has_uncommitted_changes(enterprise_root):
        raise ValueError("No changes to save in the enterprise repository")
    assert_repository_verifies(enterprise_root)
    rc, _, stderr = run_repo_git(enterprise_root, *STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage enterprise changes: {stderr}")
    rc, _, stderr = commit_with_identity(
        enterprise_root,
        message,
        author=author,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to commit enterprise changes: {stderr}")
    commit = current_commit(enterprise_root) or ""
    logger.info("Enterprise work saved: %.7s — %s", commit, message)
    return commit




def commit_engagement_work(
    engagement_root: Path,
    message: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> str:
    """Stage and commit all changes in the engagement repo. Returns the commit hash.

    Verifies the whole working tree first (it may hold manually edited files);
    a failing tree rejects the save with no commit and no state change.
    """
    from src.infrastructure.write.save_commit_verification import assert_repository_verifies  # noqa: PLC0415

    author = optional_git_author(author_name, author_email)
    if not has_uncommitted_changes(engagement_root):
        raise ValueError("No changes to save in the engagement repository")
    assert_repository_verifies(engagement_root)
    rc, _, stderr = run_repo_git(engagement_root, *STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage engagement changes: {stderr}")
    rc, _, stderr = commit_with_identity(
        engagement_root,
        message,
        author=author,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to commit engagement changes: {stderr}")
    commit = current_commit(engagement_root) or ""
    logger.info("Engagement work saved: %.7s — %s", commit, message)
    return commit


def commit_format_upgrade(repo_root: Path, message: str) -> str:
    """Commit what a persisted-format upgrade wrote, as one recognisable commit. Returns its hash.

    The caller has established that the tree was clean before the upgrade wrote, so everything staged
    is the upgrade's own output — which is why, unlike `commit_engagement_work`, this does not verify the
    whole tree first: the upgrade's steps already did, and a fixture-sized repository need not be a valid
    architecture repository to have its format recorded.
    """
    rc, _, stderr = run_repo_git(repo_root, *STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage the format upgrade: {stderr}")
    rc, _, stderr = commit_with_identity(repo_root, message, author=None)
    if rc != 0:
        raise RuntimeError(f"Failed to commit the format upgrade: {stderr}")
    commit = current_commit(repo_root) or ""
    logger.info("Format upgrade committed: %.7s — %s", commit, message)
    return commit


def push_engagement(engagement_root: Path) -> None:
    """Push the engagement repo's current branch to origin."""
    rc, _, stderr = run_repo_git(engagement_root, "push", timeout=PUSH_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"Failed to push engagement changes: {stderr}")
    logger.info("Engagement changes pushed to remote")
