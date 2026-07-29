"""REST endpoints for the repository save and review-submission workflow.

All blocking git operations (commit, push) are offloaded with asyncio.to_thread
so they do not block the event loop. Events are published to the SSE bus after
each operation so the GUI can update in real time without polling.

Endpoint overview
-----------------
GET  /api/sync/status               — per-repo sync state (uncommitted changes, branch, etc.)
POST /api/sync/engagement/save      — commit + optionally push engagement changes
POST /api/sync/enterprise/save      — commit enterprise changes to working branch
POST /api/sync/enterprise/submit    — push enterprise working branch for team review
POST /api/sync/enterprise/withdraw  — discard all pending enterprise changes
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.gui.routers import sync_status_cache

router = APIRouter()


class SaveBody(BaseModel):
    message: str
    push: bool = True
    author_name: str | None = None
    author_email: str | None = None


class WithdrawBody(BaseModel):
    confirm: bool = False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/api/sync/status")
async def sync_status() -> dict:
    """Return the cached sync state for all configured repositories."""
    return await sync_status_cache.get_sync_status()


@router.get("/api/sync/changes")
async def sync_changes(repo: str = "engagement") -> dict:
    """Return a per-artifact summary of uncommitted changes for the GUI save-dialog."""
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers.sync_changes import list_changes

    if repo == "enterprise":
        root = s.maybe_enterprise_root()
        if root is None:
            raise HTTPException(400, "Enterprise repository is not configured")
    else:
        root = s.maybe_engagement_root()
        if root is None:
            raise HTTPException(400, "Engagement repository is not configured")

    artifacts = await asyncio.to_thread(list_changes, root)
    return {"repo": repo, "artifacts": artifacts}


def _status_label(status: str) -> str:
    return {
        "synced": "Up to date",
        "accumulating": "Changes in progress",
        "pending": "Awaiting team review",
    }.get(status, status)


# ---------------------------------------------------------------------------
# Engagement: save
# ---------------------------------------------------------------------------


@router.post("/api/sync/engagement/save")
async def save_engagement(body: SaveBody) -> dict:
    """Commit (and optionally push) all engagement repository changes."""
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers.events import event_bus

    eng_root = s.maybe_engagement_root()
    if eng_root is None:
        raise HTTPException(400, "Engagement repository is not configured")

    def _save_and_push() -> str:
        commit = enterprise_git_ops.commit_engagement_work(
            eng_root,
            body.message,
            author_name=body.author_name,
            author_email=body.author_email,
        )
        if body.push:
            enterprise_git_ops.push_engagement(eng_root)
        return commit

    try:
        commit = await s.authorized_write_async(("POST", "/api/sync/engagement/save"), _save_and_push)
        sync_status_cache.invalidate_sync_status_cache(repo=eng_root)
        await event_bus.publish(
            {
                "type": "sync_engagement_saved",
                "commit": commit,
                "pushed": body.push,
                "message": body.message,
            }
        )
        return {"ok": True, "commit": commit, "pushed": body.push, "message": body.message}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Enterprise: save / submit / withdraw
# ---------------------------------------------------------------------------


@router.post("/api/sync/enterprise/save")
async def save_enterprise(body: SaveBody) -> dict:
    """Commit enterprise working-branch changes."""
    from src.infrastructure.git import enterprise_git_ops, enterprise_sync_state
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers.events import event_bus

    ent_root = s.maybe_enterprise_root()
    if ent_root is None:
        raise HTTPException(400, "Enterprise repository is not configured")

    def _branch_and_commit() -> str:
        # One write lease for the whole transaction: working branch + commit + state.
        enterprise_git_ops.ensure_working_branch(ent_root)
        return enterprise_git_ops.commit_enterprise_work(
            ent_root,
            body.message,
            author_name=body.author_name,
            author_email=body.author_email,
        )

    try:
        commit = await s.authorized_write_async(("POST", "/api/sync/enterprise/save"), _branch_and_commit)
        sync_state = enterprise_sync_state.load(ent_root)
        sync_status_cache.invalidate_sync_status_cache(repo=ent_root)
        await event_bus.publish(
            {
                "type": "sync_enterprise_saved",
                "commit": commit,
                "branch": sync_state.branch,
                "message": body.message,
            }
        )
        return {"ok": True, "commit": commit, "message": body.message}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.post("/api/sync/enterprise/submit")
async def submit_enterprise() -> dict:
    """Push the enterprise working branch for team review."""
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.git import enterprise_sync_state as es
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers.events import event_bus

    ent_root = s.maybe_enterprise_root()
    if ent_root is None:
        raise HTTPException(400, "Enterprise repository is not configured")

    sync_state = es.load(ent_root)
    if sync_state.is_pending():
        return {
            "ok": True,
            "already_submitted": True,
            "branch": sync_state.branch,
            "pushed_at": sync_state.pushed_at,
        }
    if sync_state.is_synced():
        raise HTTPException(400, "No enterprise changes to submit for review")

    try:
        branch = await s.authorized_write_async(
            ("POST", "/api/sync/enterprise/submit"), enterprise_git_ops.push_enterprise_branch, ent_root
        )
        sync_status_cache.invalidate_sync_status_cache(repo=ent_root)
        await event_bus.publish(
            {
                "type": "sync_enterprise_submitted",
                "branch": branch,
                "label": (
                    f"Enterprise changes submitted for review on branch '{branch}'. "
                    "Create a pull request in your version-control platform."
                ),
            }
        )
        return {"ok": True, "branch": branch}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.post("/api/sync/enterprise/withdraw")
async def withdraw_enterprise(body: WithdrawBody) -> dict:
    """Discard all pending enterprise changes and return the repo to main."""
    from src.infrastructure.git import enterprise_git_ops
    from src.infrastructure.gui.routers import state as s
    from src.infrastructure.gui.routers.events import event_bus

    if not body.confirm:
        raise HTTPException(
            400,
            "Set confirm=true in the request body to confirm discarding enterprise changes",
        )

    ent_root = s.maybe_enterprise_root()
    if ent_root is None:
        raise HTTPException(400, "Enterprise repository is not configured")

    try:
        branch = await s.authorized_write_async(
            ("POST", "/api/sync/enterprise/withdraw"), enterprise_git_ops.abandon_enterprise_branch, ent_root
        )
        sync_status_cache.invalidate_sync_status_cache(repo=ent_root)
        await event_bus.publish(
            {
                "type": "sync_enterprise_withdrawn",
                "discarded_branch": branch,
                "label": "Pending enterprise changes have been discarded.",
            }
        )
        return {"ok": True, "discarded_branch": branch}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
