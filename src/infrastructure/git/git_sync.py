"""Background git-sync manager: polls repos and coordinates writes around pulls.

Two repo roles are handled differently:

engagement  — fetch + pull (ff-only when clean, rebase when local commits exist).
              Rebase conflicts abort cleanly and surface a sync_conflict event.

enterprise  — state-machine-aware; the handlers live in git_sync_enterprise.py
              (see enterprise_sync_state.py for the states).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from src.infrastructure.git.fetch_attempts import (
    FetchAttempts,
    FetchDeferred,
    Fetched,
    FetchFailed,
    FetchOutcome,
    report_attempt,
)

if TYPE_CHECKING:
    from src.application.mutation_authorization import SyncHealthReason
    from src.infrastructure.git.git_auth import GitCredentials


logger = logging.getLogger(__name__)
_DEFAULT_POLL_S = 60.0
_FETCH_TIMEOUT_S = 20.0
_PULL_TIMEOUT_S = 30.0
_AUTO_UNBLOCK_S = 60.0


@dataclass
class RepoSpec:
    """A git-backed repository and its role within the two-tier model."""

    path: Path
    role: Literal["engagement", "enterprise"]


class GitSyncManager:
    def __init__(
        self,
        repos: list[RepoSpec],
        poll_interval_s: float = _DEFAULT_POLL_S,
        credentials: "GitCredentials | None" = None,
        on_repo_changed: Callable[[Path], Awaitable[None]] | None = None,
        on_health_changed: Callable[[Path], None] | None = None,
        fetch_attempts: FetchAttempts | None = None,
    ) -> None:
        self._repos = repos
        self._poll_interval_s = poll_interval_s
        self._credentials = credentials
        self._on_repo_changed = on_repo_changed
        # Injected invalidation port: persisted-health transitions must invalidate
        # cached status measurements, and only AFTER successful persistence.
        self._on_health_changed = on_health_changed
        self._task: asyncio.Task[None] | None = None
        self._askpass_script: Path | None = None
        self._last_dirty_state: dict[Path, bool] = {}
        self._last_block_reason: dict[Path, str | None] = {}
        # One record for every repository this manager polls: the deferral a refusing remote earns
        # belongs to the poll cadence, which is this object's, not to either role's sync path.
        self._fetch_attempts = fetch_attempts or FetchAttempts()

    async def start(self) -> None:
        # Credentials are verified up front at collection (collect_verified_credentials), which
        # re-prompts interactively or fails loudly on a rejection — so by the time sync starts they
        # are known-good and this only wires the askpass env and launches the poll loop.
        if self._credentials is not None:
            from src.infrastructure.git import git_env
            from src.infrastructure.git.git_auth import build_git_env, create_askpass_script

            self._askpass_script = create_askpass_script()
            git_env.set_ssh_env(build_git_env(self._credentials, self._askpass_script))
        self._task = asyncio.create_task(self._poll_loop(), name="git-sync")
        logger.info("git-sync started for %d repo(s) (poll %.1fs)", len(self._repos), self._poll_interval_s)

    def _release_askpass(self) -> None:
        """Unlink the askpass helper and clear the wired git env (idempotent)."""
        if self._askpass_script is not None:
            try:
                self._askpass_script.unlink()
            except OSError:
                pass
            self._askpass_script = None
        from src.infrastructure.git import git_env

        git_env.set_ssh_env(None)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("git-sync stopped")
        self._release_askpass()

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while True:
            for spec in self._repos:
                try:
                    if spec.role == "engagement":
                        await self._sync_engagement(spec.path)
                    else:
                        from src.infrastructure.git.git_sync_enterprise import sync_enterprise  # noqa: PLC0415

                        await sync_enterprise(self, spec.path)
                except Exception:
                    logger.exception("git sync error for %s (%s)", spec.path, spec.role)
            await asyncio.sleep(self._poll_interval_s)

    # ------------------------------------------------------------------
    # Low-level git helpers
    # ------------------------------------------------------------------

    async def _fetch_origin(self, repo: Path) -> FetchOutcome:
        """Fetch from origin unless this remote is still deferred after refusing.

        Every fetch in this manager comes through here, so a remote that is failing is attempted at
        the same decreasing rate whatever role its repository plays, and reported the same way. The
        schedule and the wording both belong to `fetch_attempts`; this contributes the attempt.
        """
        deferred = self._fetch_attempts.deferral(repo)
        if deferred is not None:
            report_attempt(repo, deferred)
            return deferred

        rc, _, err = await self._git(repo, "fetch", "origin", timeout=_FETCH_TIMEOUT_S)
        outcome: FetchOutcome = (
            self._fetch_attempts.succeeded(repo)
            if rc == 0
            else self._fetch_attempts.failed(repo, err.strip() or "unknown error")
        )
        report_attempt(repo, outcome)
        return outcome

    async def _git(self, repo: Path, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        from src.infrastructure.git.git_env import get_ssh_env

        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=repo,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=get_ssh_env(),
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return -1, "", "timeout"
        return_code = proc.returncode if proc.returncode is not None else -1
        return return_code, out.decode(errors="replace"), err.decode(errors="replace")

    async def _is_git_repo(self, path: Path) -> bool:
        rc, _, _ = await self._git(path, "rev-parse", "--git-dir")
        return rc == 0

    async def _count(self, repo: Path, range_: str) -> int:
        count = await self._rev_count(repo, range_)
        return count if count is not None else 0

    async def _rev_count(self, repo: Path, range_: str) -> int | None:
        """Commit count for ``range_``, or None when git could not evaluate it.

        The None case (invalid ref, repo error) is distinct from a genuine zero,
        so callers can surface a problem instead of silently treating it as
        "nothing to do".
        """
        rc, out, _ = await self._git(repo, "rev-list", "--count", range_)
        if rc != 0:
            return None
        try:
            return int(out.strip())
        except ValueError:
            return None

    async def _is_clean(self, repo: Path) -> bool:
        """True when nothing outside ``.arch/`` changed — runtime sync state is never work."""
        rc, out, _ = await self._git(repo, "status", "--porcelain", "--", ".", ":(exclude).arch")
        return rc == 0 and not out.strip()

    async def _upstream_ref(self, repo: Path) -> str | None:
        """Resolve the current branch's upstream (e.g. ``origin/main``), or None if unset."""
        rc, out, _ = await self._git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        ref = out.strip()
        return ref if rc == 0 and ref else None

    async def _notify_sync_blocked(self, repo: Path, reason: str) -> None:
        """Surface a non-fatal sync skip, once per distinct reason (avoids per-poll spam).

        Emitted as a dedicated ``sync_blocked`` event (no write block was taken), so the
        GUI can report the reason without the misleading "writes resume in 0s" wording.
        """
        if self._last_block_reason.get(repo) == reason:
            return
        self._last_block_reason[repo] = reason
        from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415

        logger.warning("enterprise sync blocked for %s: %s", repo, reason)
        await event_bus.publish({"type": "sync_blocked", "repo": str(repo), "reason": reason})

    def _clear_block_reason(self, repo: Path) -> None:
        self._last_block_reason[repo] = None

    async def _record_sync_blocked(self, repo: Path, reason: "SyncHealthReason", message: str) -> None:
        """Persist a typed health block, then invalidate and notify.

        Ordering is load-bearing: a failed persistence raises before any event or
        cache update, so consumers never observe health that did not durably land.
        """
        from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

        transition = await asyncio.to_thread(enterprise_sync_state.record_block, repo, reason, message)
        if transition.changed and self._on_health_changed is not None:
            self._on_health_changed(repo)
        await self._notify_sync_blocked(repo, message)

    async def _clear_sync_health(self, repo: Path) -> None:
        """Clear persisted health after a fully successful poll; invalidate + notify
        only when something actually changed."""
        from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

        transition = await asyncio.to_thread(enterprise_sync_state.clear_block, repo)
        self._clear_block_reason(repo)
        if not transition.changed:
            return
        if self._on_health_changed is not None:
            self._on_health_changed(repo)
        from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415

        await event_bus.publish({"type": "sync_status_changed", "repo": str(repo)})

    async def _notify_changed(self, repo: Path) -> None:
        if self._on_repo_changed:
            await self._on_repo_changed(repo)

    async def _auto_unblock(self, repo: Path, delay_s: float, was_blocked: bool) -> None:
        await asyncio.sleep(delay_s)
        if not was_blocked:
            from src.infrastructure.rest.routers.events import event_bus
            from src.infrastructure.workspace.write_block_manager import unblock_repo

            unblock_repo(repo)
            await event_bus.publish({"type": "write_block_changed", "repo": str(repo), "blocked": False})
            logger.info("auto-unblock completed for %s", repo)

    # ------------------------------------------------------------------
    # Engagement
    # ------------------------------------------------------------------

    async def _publish_dirty_state_change(self, repo: Path, *, is_dirty: bool) -> None:
        from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415

        if is_dirty != self._last_dirty_state.get(repo, False):
            self._last_dirty_state[repo] = is_dirty
            await event_bus.publish({"type": "sync_status_changed", "repo": str(repo)})

    async def _sync_engagement(self, repo: Path) -> None:
        from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415
        from src.infrastructure.workspace.mutation_gate import get_workspace_gate  # noqa: PLC0415

        if not await self._is_git_repo(repo):
            return

        is_clean = await self._is_clean(repo)
        await self._publish_dirty_state_change(repo, is_dirty=not is_clean)

        match await self._fetch_origin(repo):
            case FetchDeferred() | FetchFailed():
                return
            case Fetched():
                pass

        behind = await self._count(repo, "HEAD..@{u}")
        if behind == 0:
            return
        ahead = await self._count(repo, "@{u}..HEAD")
        if not is_clean and ahead == 0:
            logger.info("skipping engagement pull %s: uncommitted changes", repo)
            return

        rc, head_out, _ = await self._git(repo, "rev-parse", "HEAD")
        old_sha = head_out.strip()
        rc, branch_out, _ = await self._git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        branch = branch_out.strip()
        gate = get_workspace_gate()
        if gate.block_reason == "read_only":
            return

        from src.infrastructure.git.git_sync_m4 import (  # noqa: PLC0415
            add_detached_worktree,
            prepare_rebase_worktree,
            run_m4_pull,
        )

        await event_bus.publish({"type": "sync_pull_started", "repo": str(repo), "behind": behind})
        try:
            with gate.blocking_writes("sync_in_progress"):
                if ahead > 0:
                    rebase_result = await prepare_rebase_worktree(self._git, repo, old_sha, timeout=_PULL_TIMEOUT_S)
                    if rebase_result is None:
                        await event_bus.publish(
                            {"type": "sync_conflict", "repo": str(repo), "error": "rebase conflict"}
                        )
                        return
                    worktree_path, new_sha = rebase_result
                else:
                    rc, new_sha_out, _ = await self._git(repo, "rev-parse", "@{u}")
                    new_sha = new_sha_out.strip()
                    worktree_path = await add_detached_worktree(self._git, repo, new_sha, timeout=_PULL_TIMEOUT_S)
                try:
                    run_m4_pull(repo, worktree_path, branch=branch, old_sha=old_sha, new_sha=new_sha, gate=gate)
                finally:
                    await self._git(repo, "worktree", "remove", "--force", str(worktree_path))
                await self._git(repo, "reset", "--mixed", "HEAD")
        except Exception as exc:
            logger.exception("pull error for engagement %s", repo)
            await event_bus.publish({
                "type": "sync_pull_failed", "repo": str(repo), "error": str(exc),
                "auto_unblock_in_seconds": 0,
            })
            return

        await event_bus.publish({"type": "sync_pull_completed", "repo": str(repo), "commits_pulled": behind})
        await self._notify_changed(repo)
