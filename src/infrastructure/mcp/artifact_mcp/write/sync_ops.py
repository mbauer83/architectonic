"""MCP write tools: save, submit, and withdraw architecture work.

Three tools manage the git persistence lifecycle for both repositories:

  artifact_save_changes      — commit accumulated file changes (engagement or enterprise)
  artifact_submit_for_review — push the enterprise working branch for team review
  artifact_withdraw_changes  — abandon the enterprise working branch (irreversible)

These tools operate on the repositories configured via arch-workspace.yaml and
resolved at startup; no explicit repo-path arguments are required.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.tool_annotations import (
    DESTRUCTIVE_OPEN_WORLD_WRITE,
    OPEN_WORLD_WRITE,
)


def artifact_save_changes(
    *,
    message: str,
    target: str = "engagement",
    push: bool = True,
    author_name: str | None = None,
    author_email: str | None = None,
) -> dict[str, object]:
    """Commit all accumulated architecture changes to the repository.

    target='engagement' (default) commits and optionally pushes to the engagement
    repo. target='enterprise' commits the enterprise working branch (use
    artifact_submit_for_review to push it for team review).
    push=True (default) pushes the engagement repo after committing; has no
    effect for the enterprise target.
    """
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.rest.routers.state import maybe_engagement_root, maybe_enterprise_root

    if target not in ("engagement", "enterprise"):
        return {"ok": False, "error": "target must be 'engagement' or 'enterprise'"}

    try:
        if target == "engagement":
            eng_root = maybe_engagement_root()
            if eng_root is None:
                return {"ok": False, "error": "Engagement repository is not initialised"}
            commit = enterprise_git_ops.commit_engagement_work(
                eng_root,
                message,
                author_name=author_name,
                author_email=author_email,
            )
            if push:
                enterprise_git_ops.push_engagement(eng_root)
            return {
                "ok": True,
                "target": "engagement",
                "commit": commit,
                "pushed": push,
                "message": message,
            }
        else:
            ent_root = maybe_enterprise_root()
            if ent_root is None:
                return {"ok": False, "error": "Enterprise repository is not configured"}
            enterprise_git_ops.ensure_working_branch(ent_root)
            commit = enterprise_git_ops.commit_enterprise_work(
                ent_root,
                message,
                author_name=author_name,
                author_email=author_email,
            )
            return {
                "ok": True,
                "target": "enterprise",
                "commit": commit,
                "pushed": False,
                "message": message,
                "next_step": ("Use artifact_submit_for_review to push this branch for team review."),
            }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


def artifact_submit_for_review() -> dict[str, object]:
    """Push the enterprise working branch so it can be reviewed and merged by the team.

    After submitting, create a pull request from the returned branch name in
    your version-control hosting platform (GitHub, GitLab, etc.).
    The system automatically detects when the branch is merged into main and
    updates the enterprise repository view accordingly.
    """
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.git.enterprise_sync_state import load as load_state
    from src.infrastructure.rest.routers.state import maybe_enterprise_root

    ent_root = maybe_enterprise_root()
    if ent_root is None:
        return {"ok": False, "error": "Enterprise repository is not configured"}

    state = load_state(ent_root)
    if state.is_pending():
        return {
            "ok": True,
            "already_submitted": True,
            "branch": state.branch,
            "pushed_at": state.pushed_at,
            "message": (
                "Branch was already submitted. Waiting for team review. The system will detect when it is merged."
            ),
        }
    if state.is_synced():
        return {
            "ok": False,
            "error": ("No enterprise changes to submit. Make and save some changes first, then submit for review."),
        }

    try:
        branch = enterprise_git_ops.push_enterprise_branch(ent_root)
        return {
            "ok": True,
            "branch": branch,
            "message": (
                f"Enterprise changes pushed to branch '{branch}'. "
                "Create a pull request from this branch in your version-control platform "
                "to request a team review. The system will automatically detect when it is merged."
            ),
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


def artifact_withdraw_changes(*, confirm: bool = False) -> dict[str, object]:
    """Permanently discard all pending enterprise changes that have not yet been merged.

    This cannot be undone. Pass confirm=True to confirm. Only the enterprise
    repository is affected; engagement repository changes are never discarded.
    """
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.rest.routers.state import maybe_enterprise_root

    if not confirm:
        return {
            "ok": False,
            "error": "Pass confirm=True to confirm discarding all pending enterprise changes.",
        }

    ent_root = maybe_enterprise_root()
    if ent_root is None:
        return {"ok": False, "error": "Enterprise repository is not configured"}

    try:
        branch = enterprise_git_ops.abandon_enterprise_branch(ent_root)
        return {
            "ok": True,
            "discarded_branch": branch,
            "message": "All pending enterprise changes have been discarded.",
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_save_changes,
        name="artifact_save_changes",
        title="Save Changes",
        description=(
            "Commit all accumulated architecture changes. target='engagement' (default) saves "
            "to the engagement repository and pushes to the remote (push=true is the DEFAULT; "
            "pass push=false to commit locally only). "
            "target='enterprise' commits changes to the enterprise working branch "
            "(use artifact_submit_for_review to push it for team review). "
            "Optional author_name and author_email set the commit author; the configured "
            "service identity remains the committer."
        ),
        annotations=OPEN_WORLD_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_submit_for_review,
        name="artifact_submit_for_review",
        title="Submit Enterprise Changes for Review",
        description=(
            "Push the enterprise working branch to the remote for team review. "
            "Returns the branch name; create a pull request from it in your "
            "version-control platform. The system auto-detects when it is merged."
        ),
        annotations=OPEN_WORLD_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_withdraw_changes,
        name="artifact_withdraw_changes",
        title="Withdraw Enterprise Changes",
        description=(
            "Permanently discard all pending enterprise changes (requires confirm=True). "
            "Only affects the enterprise repository. Cannot be undone."
        ),
        annotations=DESTRUCTIVE_OPEN_WORLD_WRITE,  # deletes the REMOTE review branch
        structured_output=True,
    )
