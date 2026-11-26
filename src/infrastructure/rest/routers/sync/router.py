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
PUT  /api/sync/credentials          — supply a git credential a remote asked for (local operator only)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from src.infrastructure.git.credential_refusal import GitCredentialsRequired
from src.infrastructure.rest.contracts.error_responses import (
    GIT_CREDENTIALS_REQUIRED_STATUS,
    git_credentials_error,
)
from src.infrastructure.rest.contracts.errors import ApiError, DenialDetails
from src.infrastructure.rest.contracts.operator_request import (
    OPERATOR_REQUEST_HEADER,
    is_local_operator_request,
)
from src.infrastructure.rest.contracts.platform import SyncStatusResponse
from src.infrastructure.rest.contracts.sync import (
    EngagementSaveResponse,
    EnterpriseSaveResponse,
    EnterpriseSubmitResponse,
    EnterpriseWithdrawResponse,
    SyncChangesResponse,
)
from src.infrastructure.rest.routers._openapi import TAG_SYNC, error_response
from src.infrastructure.rest.routers.sync import status_cache as sync_status_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=[TAG_SYNC])

#: Every operation here that reaches the remote can be refused for want of a git credential.
_CREDENTIALS_RESPONSES: dict[int | str, dict[str, object]] = {
    GIT_CREDENTIALS_REQUIRED_STATUS: error_response(
        "`git_credentials_required`: the remote refused for want of a credential. Supply it with "
        "`PUT /api/sync/credentials` and repeat the request"
    ),
}


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


@router.get("/api/sync/status", response_model=SyncStatusResponse)
async def sync_status() -> dict:
    """Return the cached sync state for all configured repositories."""
    return await sync_status_cache.get_sync_status()


@router.get("/api/sync/changes", response_model=SyncChangesResponse)
async def sync_changes(repo: Literal["engagement", "enterprise"] = "engagement") -> dict:
    """Return a per-artifact summary of uncommitted changes for the GUI save-dialog.

    ``repo`` is a closed vocabulary rather than a string: the branch below treats everything that is
    not ``enterprise`` as the engagement repository, so an unrecognised name used to be answered with
    the wrong repository's changes and its own name echoed back as though it had been understood. It is
    a typed 422 now.
    """
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.rest.routers.sync.changes import list_changes

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


@router.post("/api/sync/engagement/save", response_model=EngagementSaveResponse,
    response_model_exclude_none=True, responses=_CREDENTIALS_RESPONSES)
async def save_engagement(body: SaveBody) -> dict:
    """Commit (and optionally push) all engagement repository changes."""
    from src.infrastructure.git import git_work_commits
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.rest.routers.events import event_bus

    eng_root = s.maybe_engagement_root()
    if eng_root is None:
        raise HTTPException(400, "Engagement repository is not configured")

    def _save_and_push() -> str:
        return git_work_commits.save_engagement_work(
            eng_root,
            body.message,
            push=body.push,
            author_name=body.author_name,
            author_email=body.author_email,
        )

    try:
        commit = await s.authorized_write_async(
            "sync_save_engagement", _save_and_push)
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
    except GitCredentialsRequired:
        raise  # answered as `git_credentials_required` by its own handler
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Enterprise: save / submit / withdraw
# ---------------------------------------------------------------------------


@router.post("/api/sync/enterprise/save", response_model=EnterpriseSaveResponse,
    response_model_exclude_none=True)
async def save_enterprise(body: SaveBody) -> dict:
    """Commit enterprise working-branch changes."""
    from src.infrastructure.git import enterprise_branch_lifecycle, enterprise_sync_state, git_work_commits
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.rest.routers.events import event_bus

    ent_root = s.maybe_enterprise_root()
    if ent_root is None:
        raise HTTPException(400, "Enterprise repository is not configured")

    def _branch_and_commit() -> str:
        # One write lease for the whole transaction: working branch + commit + state.
        enterprise_branch_lifecycle.ensure_working_branch(ent_root)
        return git_work_commits.commit_enterprise_work(
            ent_root,
            body.message,
            author_name=body.author_name,
            author_email=body.author_email,
        )

    try:
        commit = await s.authorized_write_async(
            "sync_save_enterprise", _branch_and_commit)
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
    except GitCredentialsRequired:
        raise  # answered as `git_credentials_required` by its own handler
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.post("/api/sync/enterprise/submit", response_model=EnterpriseSubmitResponse,
    response_model_exclude_none=True, responses=_CREDENTIALS_RESPONSES)
async def submit_enterprise() -> dict:
    """Push the enterprise working branch for team review."""
    from src.infrastructure.git import enterprise_branch_lifecycle
    from src.infrastructure.git import enterprise_sync_state as es
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.rest.routers.events import event_bus

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
            "sync_submit_enterprise", enterprise_branch_lifecycle.push_enterprise_branch, ent_root
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
        return {"ok": True, "branch": branch, "review_url": _review_url(ent_root, branch)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except GitCredentialsRequired:
        raise  # answered as `git_credentials_required` by its own handler
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


@router.post("/api/sync/enterprise/withdraw", response_model=EnterpriseWithdrawResponse,
    response_model_exclude_none=True, responses=_CREDENTIALS_RESPONSES)
async def withdraw_enterprise(body: WithdrawBody) -> dict:
    """Discard all pending enterprise changes and return the repo to main."""
    from src.infrastructure.git import enterprise_branch_lifecycle
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.rest.routers.events import event_bus

    if not body.confirm:
        raise HTTPException(
            400,
            "Set confirm=true in the request body to confirm discarding enterprise changes",
        )

    ent_root = s.maybe_enterprise_root()
    if ent_root is None:
        raise HTTPException(400, "Enterprise repository is not configured")

    def _abandon_and_settle() -> str | None:
        # One unit of work, inside the write queue. Abandoning the branch and settling the changes
        # it carried are one transition — a withdrawal that ran the first and left the second to a
        # request thread would put a file write outside the serialisation every other write uses,
        # and would leave a window where the branch is gone and the changes still read `submitted`.
        discarded = enterprise_branch_lifecycle.abandon_enterprise_branch(ent_root)
        _settle_the_withdrawn_changes()
        return discarded

    try:
        branch = await s.authorized_write_async("sync_withdraw_enterprise", _abandon_and_settle)
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
    except GitCredentialsRequired:
        raise  # answered as `git_credentials_required` by its own handler
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))


def _review_url(enterprise_root: Path, branch: str) -> str | None:
    """The platform's new-pull-request page for `branch` against the enterprise base branch.

    Returned by a fresh submit only; an already-pending one is answered without it, and the sync
    status carries it for as long as the review is pending.
    """
    from src.infrastructure.git.git_repository_state import UPSTREAM_BRANCH
    from src.infrastructure.git.review_link import review_url_for

    return review_url_for(enterprise_root, branch=branch, base=UPSTREAM_BRANCH)


def _settle_the_withdrawn_changes() -> None:
    """The changes the discarded branch was carrying, reconciled where they now stand."""
    from src.infrastructure.rest.routers import state as s
    from src.infrastructure.write.artifact_write.integration_cleanup import settle_after_a_withdrawal

    settle_after_a_withdrawal(s.maybe_get_repo())


# ---------------------------------------------------------------------------
# Credentials a remote asked for
# ---------------------------------------------------------------------------


class SyncCredentialsBody(BaseModel):
    """A credential for one protocol. `secret` is the SSH key passphrase or the HTTPS token.

    `SecretStr`, so the value is masked wherever the model is printed; the validation-error
    envelope reports field paths and messages only, never the input.
    """

    protocol: Literal["ssh", "https"]
    secret: SecretStr = Field(min_length=1, max_length=4096)
    #: HTTPS only. Hosts that ignore it for token authentication accept the default.
    username: str | None = Field(default=None, max_length=256)


@router.put(
    "/api/sync/credentials",
    status_code=204,
    response_class=Response,
    responses={
        403: error_response(
            "The request is not a local operator request: one from the loopback carrying "
            f"`{OPERATOR_REQUEST_HEADER}`, as the GUI served by this backend sends"
        ),
        GIT_CREDENTIALS_REQUIRED_STATUS: error_response(
            "`git_credentials_required` with `rejected: true`: a remote that uses this protocol "
            "refused the credential, which is not kept"
        ),
    },
)
def supply_sync_credentials(
    request: Request,
    body: SyncCredentialsBody,
    operator_request: Annotated[
        str | None,
        Header(
            alias=OPERATOR_REQUEST_HEADER,
            description="`1` from the GUI or command line on this machine; any other request is refused",
        ),
    ] = None,
) -> Response:
    """Hold a git credential for this process, after the remotes that use it have accepted it.

    The GUI sends this when a save, submit or discard was refused with `git_credentials_required`,
    then repeats the operation. The credential is kept in memory until the backend stops: it is
    never written to disk, logged, or returned, and nothing answers with it.

    Accepted only as a local operator request (`operator_request`), the gate `arch-assurance unlock`
    uses: from the loopback, carrying the operator header, which a page from another origin cannot
    send. A deployment reached through a proxy therefore cannot be handed a credential this way.

    There is deliberately no MCP tool for this. An agent session would have to hold the secret in
    its context and transcript to pass it on; MCP callers are told to have the person enter it in
    the GUI or to set the environment variable before the backend starts.
    """
    from src.infrastructure.git import held_credentials  # noqa: PLC0415
    from src.infrastructure.rest.routers import state as s  # noqa: PLC0415

    # Declared so the published document names the header a client must send; the gate below reads
    # the request itself, so the loopback condition is checked with it.
    del operator_request
    if not is_local_operator_request(request):
        raise ApiError(
            403, "forbidden",
            "A git credential is accepted only from the GUI or command line on the machine the "
            "backend runs on.",
            DenialDetails(reason_code="operator_request_required"),
        )
    roots = [root for root in (s.maybe_engagement_root(), s.maybe_enterprise_root()) if root is not None]
    try:
        held_credentials.supply(
            body.protocol,
            secret=body.secret.get_secret_value(),
            username=body.username,
            verify_against=roots,
        )
    except GitCredentialsRequired as refused:
        raise git_credentials_error(refused) from None
    sync_status_cache.invalidate_sync_status_cache()
    return Response(status_code=204)
