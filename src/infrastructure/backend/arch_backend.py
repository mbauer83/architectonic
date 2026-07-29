"""Unified FastAPI + MCP backend entry point."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.artifact_query import ArtifactRepository

import uvicorn

from src.config.settings import backend_min_log_level
from src.infrastructure.backend._startup_id_checks import (
    assert_no_cross_repo_id_collisions,
    assert_no_duplicate_short_ids,
)
from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.backend.backend_control import backend_status, stop_backend
from src.infrastructure.backend.backend_probe import probe_backend, resolve_backend_port
from src.infrastructure.backend.backend_state import (
    backend_log_path,
    read_backend_state,
    remove_backend_state,
    write_backend_state,
)
from src.infrastructure.gui import gui_server

logger = logging.getLogger(__name__)


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    from src.infrastructure.git.git_auth import register_token_file

    parser = _build_parser()
    args = parser.parse_args(argv)
    register_token_file(args.git_token_file)

    if not (args.status or args.stop) and _is_background_tty_job():
        log_path = _redirect_stdio_to_backend_log(start=Path.cwd())
        print(f"arch-backend detected a background TTY job; redirecting output to {log_path}")

    log_level = getattr(logging, backend_min_log_level(), logging.INFO)
    logging.basicConfig(
        level=logging.CRITICAL if args.status else log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    resolved_port = resolve_backend_port(start=Path.cwd(), explicit_port=args.port)

    if args.status:
        _run_status(resolved_port)
        return
    if args.stop:
        _run_stop(args, resolved_port)
        return
    if args.restart:
        _stop_for_restart(resolved_port)
    if args.daemon:
        _run_daemon(args, resolved_port, argv)
        return
    _run_foreground(args, parser, resolved_port)


# ── Argument parsing ──────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Unified architecture backend")
    p.add_argument("--repo-root", default=None,
                   help="Engagement repository root (default: ARCH_REPO_ROOT or arch-init state)")
    p.add_argument("--enterprise-root", default=None,
                   help="Enterprise repository root (default: ARCH_ENTERPRISE_ROOT or arch-init state)")
    p.add_argument("--admin-mode", action="store_true", default=False,
                   help="Enable enterprise-repo writes through /admin/api/*")
    p.add_argument("--read-only", action="store_true", default=False,
                   help="Block all engagement-repo writes (use for shared/review deployments)")
    p.add_argument("--stop", action="store_true", default=False,
                   help="Stop the currently running arch-backend for this workspace")
    p.add_argument("--status", action="store_true", default=False,
                   help="Show whether arch-backend is running for this workspace")
    p.add_argument("--restart", action="store_true", default=False,
                   help="Stop the running backend before starting a new one")
    p.add_argument("--daemon", action="store_true", default=False,
                   help="Start arch-backend detached with output in .arch/backend.log")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--git-token-file", default=None, metavar="PATH",
                   help="Read the HTTPS personal access token from this file (alternative to "
                        "ARCH_GIT_HTTPS_TOKEN; keeps the secret out of the environment)")
    return p


# ── Background-TTY utilities ──────────────────────────────────────────────────

def _is_background_tty_job() -> bool:
    try:
        return sys.stderr.isatty() and os.tcgetpgrp(sys.stderr.fileno()) != os.getpgrp()
    except OSError:
        return False


def _redirect_stdio_to_backend_log(*, start: Path | None = None) -> Path:
    log_path = backend_log_path(start)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    null_fd = os.open(os.devnull, os.O_RDONLY)
    try:
        os.dup2(null_fd, sys.stdin.fileno())
        os.dup2(log_fd, sys.stdout.fileno())
        os.dup2(log_fd, sys.stderr.fileno())
    finally:
        if log_fd > 2:
            os.close(log_fd)
        if null_fd > 2:
            os.close(null_fd)
    return log_path


# ── Status command ────────────────────────────────────────────────────────────

def _status_headline(result: dict) -> str:
    """One-line status summary derived from the backend_status result."""
    p, pid = result.get("port"), result.get("pid")
    if result.get("running"):
        return f"backend is running on port {p} (pid {pid})"
    messages: dict[object, str] = {
        "unmanaged_backend": f"backend responding on port {p} but not managed by this workspace",
        "port_in_use": f"port {p} is in use by another process",
        "not_running": "backend is not running",
        "stopped_backend": f"backend process pid {pid} is stopped on port {p}",
        "unhealthy_backend": f"backend process pid {pid} is not responding on port {p}",
        "stale_pid": f"removed stale backend pid {pid}",
        "invalid_state": "backend state is invalid",
    }
    return messages.get(result.get("reason"), f"backend is not healthy on port {p} (pid {pid})")


def _run_status(resolved_port: int) -> None:
    result = backend_status(port=resolved_port)
    print(_status_headline(result))
    if ps := result.get("process_state"):
        print(f"  process state: {ps}")
    if stdio := " ".join(f"{k}={result[k]}" for k in ("stdin", "stdout", "stderr") if result.get(k) is not None):
        print(f"  stdio: {stdio}")
    if lp := result.get("log_path"):
        print(f"  log: {lp}")

# ── Stop command ──────────────────────────────────────────────────────────────

def _run_stop(args: argparse.Namespace, resolved_port: int) -> None:
    result = stop_backend(port=resolved_port)
    reason = result.get("reason")
    if result.get("stopped"):
        _print_stopped(result)
    elif reason == "not_running":
        print("backend is not running")
    elif reason == "stale_pid":
        print(f"removed stale backend pid {result.get('pid')}")
    elif reason == "invalid_state":
        print("removed invalid backend state")
    elif reason == "single_other_port":
        pid = result.get("pid")
        if not isinstance(pid, int):
            raise SystemExit("failed to determine backend pid")
        other_port = result.get("port")
        if _confirm_stop_other_instance(expected_port=resolved_port, pid=pid, actual_port=other_port):
            follow_up = stop_backend(port=int(other_port) if isinstance(other_port, int) else None)
            if follow_up.get("stopped"):
                _print_stopped(follow_up)
            else:
                raise SystemExit(f"failed to stop backend pid {follow_up.get('pid')}")
        else:
            raise SystemExit(1)
    else:
        raise SystemExit(f"failed to stop backend pid {result.get('pid')}")


def _print_stopped(result: dict) -> None:
    pids = result.get("pids")
    if isinstance(pids, list) and len(pids) > 1:
        print(f"stopped backend pids {', '.join(str(p) for p in pids)}")
    else:
        print(f"stopped backend pid {result.get('pid')}")


def _confirm_stop_other_instance(*, expected_port: int, pid: int, actual_port: object) -> bool:
    if not sys.stdin.isatty():
        print(f"found arch-backend on port {actual_port} (pid {pid}); configured port is {expected_port}. "
              f"Rerun interactively or pass --port {actual_port}")
        return False
    try:
        return input(f"Backend on port {actual_port} (pid {pid}), configured port is {expected_port}. "
                     f"Stop it? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def _stop_for_restart(resolved_port: int) -> None:
    result = stop_backend(port=resolved_port)
    if result.get("stopped"):
        _print_stopped(result)
    elif result.get("reason") not in {"not_running", "stale_pid", "invalid_state"}:
        raise SystemExit(f"failed to restart backend pid {result.get('pid')}")


# ── Pre-start guard (shared by daemon and foreground) ─────────────────────────

def _guard_prestart(resolved_port: int, *, for_daemon: bool, restart: bool) -> bool:
    """Return False if startup should abort (already running); raise SystemExit on fatal conditions."""
    existing = read_backend_state()
    if existing is not None:
        existing_port = existing.get("port")
        if isinstance(existing_port, int) and probe_backend(existing_port):
            print(f"backend already running on port {existing_port}")
            return False

    status = backend_status(port=resolved_port)
    if status.get("running"):
        print(f"backend already running on port {status.get('port')} (pid {status.get('pid')})")
        return False
    if status.get("reason") in {"stopped_backend", "unhealthy_backend"}:
        if for_daemon and restart:
            cleanup = stop_backend(port=resolved_port)
            if not cleanup.get("stopped") and cleanup.get("reason") not in {"not_running", "stale_pid"}:
                raise SystemExit(
                    f"arch-backend pid {status.get('pid')} is not healthy and could not be stopped; "
                    "run 'arch-backend --stop' manually"
                )
        else:
            suffix = " or 'arch-backend --restart --daemon'" if for_daemon else " or 'arch-backend --restart'"
            raise SystemExit(
                f"arch-backend pid {status.get('pid')} is on port {resolved_port} but is not healthy; "
                f"run 'arch-backend --stop'{suffix}"
            )
    if status.get("reason") == "unmanaged_backend":
        print(f"backend already responding on port {resolved_port} but is not managed by this workspace")
        return False
    if status.get("reason") == "port_in_use":
        raise SystemExit(f"port {resolved_port} is already in use by another process")
    return True


# ── Daemon command ────────────────────────────────────────────────────────────

def _get_git_credentials():  # type: ignore[no-untyped-def]
    from src.infrastructure.backend.arch_backend_app import find_git_repos
    from src.infrastructure.git.git_auth import collect_verified_credentials
    # Verify up front: a wrong interactively-entered passphrase re-prompts until valid (or Ctrl-C);
    # a wrong environment/non-interactive credential fails loudly instead of starting sync broken.
    return collect_verified_credentials([r.path for r in find_git_repos()])


def _run_daemon(args: argparse.Namespace, resolved_port: int, argv: list[str] | None) -> None:
    if not _guard_prestart(resolved_port, for_daemon=True, restart=args.restart):
        return
    creds = _get_git_credentials()
    if creds is not None:
        from src.infrastructure.git.git_auth import credentials_to_env_overrides
        os.environ.update(credentials_to_env_overrides(creds))
    log_path = backend_log_path(Path.cwd())
    pid = _start_daemon(argv=argv, log_path=log_path)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if probe_backend(resolved_port):
            print(f"backend started on port {resolved_port} (pid {pid}); log: {log_path}")
            return
        time.sleep(0.25)
    raise SystemExit(f"timed out waiting for backend on port {resolved_port}; see {log_path}")


def _start_daemon(*, argv: list[str] | None, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(
            [sys.argv[0], *_daemon_argv(argv)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=str(Path.cwd()),
        )
    return int(proc.pid)


def _daemon_argv(argv: list[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    return [arg for arg in raw if arg not in ("--daemon", "--restart", "--stop")]


# ── Foreground server ─────────────────────────────────────────────────────────

def _run_foreground(args: argparse.Namespace, parser: argparse.ArgumentParser, resolved_port: int) -> None:
    if not _guard_prestart(resolved_port, for_daemon=False, restart=False):
        return
    repo_root_path, enterprise_root_path = gui_server.resolve_server_roots(args.repo_root, args.enterprise_root)
    if repo_root_path is None:
        parser.error(
            "No --repo-root given, ARCH_REPO_ROOT not set, and no .arch/init-state.yaml found. Run arch-init first.")

    repo = _initialise_repo(repo_root_path, enterprise_root_path, args)
    _run_startup_validations(repo)
    _configure_server_state(repo, repo_root_path, enterprise_root_path, args)

    app = _build_app(credentials=_get_git_credentials())
    write_backend_state(port=resolved_port)
    logger.info("Backend state file written for pid=%s port=%s", os.getpid(), resolved_port)
    try:
        uvicorn.run(app, host=args.host, port=resolved_port, log_level=backend_min_log_level().lower())
    except Exception:
        logger.exception("arch-backend terminated during startup")
        raise
    finally:
        logger.info("Removing backend state file")
        remove_backend_state()


def _initialise_repo(
    repo_root_path: Path, enterprise_root_path: Path | None, args: argparse.Namespace
) -> "ArtifactRepository":
    from src.application.artifact_query import ArtifactRepository
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
    from src.infrastructure.backend._group_registry_startup import repair_group_registries
    from src.infrastructure.backend._profile_registry_startup import validate_profile_registries
    from src.infrastructure.write.artifact_write.m4_transaction import recover_transactions

    roots = [p for p in (repo_root_path, enterprise_root_path) if p is not None]
    logger.info("Initializing backend — repo_root=%s enterprise_root=%s admin_mode=%s read_only=%s",
                repo_root_path, enterprise_root_path, args.admin_mode, args.read_only)
    index = (
        combined_artifact_index(repo_root_path, enterprise_root_path)
        if enterprise_root_path is not None
        else shared_artifact_index(repo_root_path)
    )
    # Startup ordering (WS9): recover durable transactions → repair group registry (mutates
    # files) → build index → duplicate scan → serve.  Group repair must precede the index
    # build so the index is consistent with disk at first served request (INV-2); the
    # duplicate scan fails closed on a genuine cross-mount collision (INV-1/WS2).
    for root in roots:
        recovered = recover_transactions(root, rebuild_index=index.refresh)
        if recovered:
            logger.warning("Recovered %s durable transaction(s) in %s", recovered, root)
    repair_group_registries(repo_root_path, enterprise_root_path)
    # Class A profile-registry validation before the index build: a malformed registry or an
    # undefined binding makes the profile subsystem untrustworthy (engagement aborts,
    # enterprise warns) — mirrors the group-registry posture above (WU-Q1).
    validate_profile_registries(repo_root_path, enterprise_root_path)
    repo = ArtifactRepository(
        index,
        excluded_entity_types=build_runtime_catalogs(get_module_registry()).ontology.entity_types_with_class(
            "internal"
        ),
    )
    repo.refresh()
    assert_no_duplicate_short_ids(index)
    assert_no_cross_repo_id_collisions(index)
    return repo


def _run_startup_validations(repo: "ArtifactRepository") -> None:
    from src.application.startup_validation import (
        RepoCompatibilityError,
        SchemaPolicyError,
        validate_repo_compatibility,
        validate_schema_policy,
    )
    from src.infrastructure.app_bootstrap import build_module_registry, get_module_registry

    try:
        # Compare against the complete vocabulary (all modules, enabled or not) so that
        # artifacts belonging to a merely-disabled optional module (e.g. assurance diagrams
        # when no confidential store is configured) warn rather than abort startup.
        warnings = validate_repo_compatibility(
            repo,
            get_module_registry(),
            complete_registry=build_module_registry(complete_vocabulary=True),
        )
        for warning in warnings:
            logger.warning("Repository compatibility: %s", warning)
    except RepoCompatibilityError as exc:
        logger.error("Startup aborted — repository uses types not in the module registry:\n%s", exc)
        sys.exit(1)

    try:
        for warning in validate_schema_policy(repo):
            logger.warning("Schema policy: %s", warning)
    except SchemaPolicyError as exc:
        logger.error("Startup aborted — attribute-schema policy violations:\n%s", exc)
        sys.exit(1)


def _configure_server_state(
    repo: "ArtifactRepository", repo_root_path: Path, enterprise_root_path: Path | None, args: argparse.Namespace
) -> None:
    from src.application.artifact_document_schema import load_document_schemata
    from src.infrastructure.gui.routers import state as gui_state
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import install_mutation_executor
    from src.infrastructure.workspace.mutation_gate import get_workspace_gate
    from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
    from src.infrastructure.write.workspace_authorization import (
        WorkspaceAuthorizationSnapshots,
        persisted_sync_health,
    )

    gui_state.init_state(
        repo, repo_root_path, enterprise_root_path, admin_mode=args.admin_mode, read_only=args.read_only
    )
    load_document_schemata(repo_root_path)
    health_kwargs = (
        {"sync_health": persisted_sync_health(enterprise_root_path)} if enterprise_root_path is not None else {}
    )
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=repo_root_path,
                enterprise_root=enterprise_root_path,
                admin_mode=args.admin_mode,
                read_only=args.read_only,
                gate=get_workspace_gate(),
                **health_kwargs,
            )
        )
    )
    if args.read_only:
        from src.infrastructure.workspace.write_block_manager import block_repo
        block_repo(repo_root_path, reason="read_only")

if __name__ == "__main__":
    main()
