"""
workspace_init.py — CLI tool for initializing architecture workspace.

Reads ``arch-workspace.yaml``, validates / clones git repos, and writes
``.arch/init-state.yaml`` so that MCP + GUI servers can resolve repo paths.

Usage::

    arch-init                     # find arch-workspace.yaml in CWD or parents
    arch-init --config /path/to/arch-workspace.yaml

Exit codes:
    0  — success
    1  — configuration or git error (message printed to stderr)
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import yaml

from src.application.repo_path_helpers import all_model_roots
from src.config.repo_paths import MODEL, PROJECTS
from src.config.settings import (
    repo_init_commit_author_email,
    repo_init_commit_author_name,
)
from src.config.workspace_paths import (
    CONFIG_FILENAME,
    STATE_DIR,
    STATE_FILENAME,
)
from src.config.workspace_paths import (
    find_workspace_config as _find_config,
)
from src.config.workspace_paths import (
    load_workspace_state as _load_workspace_state,
)
from src.config.workspace_paths import (
    parse_workspace_config as _parse_config,
)
from src.infrastructure.workspace import git_remote

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(
    args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _current_branch(repo: Path) -> str | None:
    r = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    if r.returncode == 0:
        branch = r.stdout.strip()
        if branch and branch != "HEAD":
            return branch

    # Freshly initialized repositories may have an unborn HEAD, in which case
    # rev-parse fails even though the configured branch is already selected.
    fallback = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=repo)
    if fallback.returncode == 0:
        branch = fallback.stdout.strip()
        return branch or None
    return None


def _is_dirty(repo: Path) -> bool:
    r = _run_git(["status", "--porcelain"], cwd=repo)
    return bool(r.stdout.strip())


def _has_commits(repo: Path) -> bool:
    r = _run_git(["rev-parse", "--verify", "HEAD"], cwd=repo)
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------


def _verify_working_tree(
    ctx: git_remote.BootstrapContext,
    *,
    allow_dirty_git_repo: bool,
    allow_dirty_uncommitted_git_repo: bool,
) -> None:
    """Apply the dirty-working-tree policy to an existing clone."""
    dest, branch = ctx.dest, ctx.branch
    if not _is_dirty(dest):
        print(f"  {ctx.label}: existing clone OK ({dest}, branch={branch})")
        return
    if allow_dirty_git_repo:
        print(f"  {ctx.label}: using existing dirty git repo ({dest}, branch={branch})")
        return
    if allow_dirty_uncommitted_git_repo and not _has_commits(dest):
        print(f"  {ctx.label}: using newly scaffolded git repo ({dest}, branch={branch}, no commits yet)")
        return
    raise SystemExit(
        f"ERROR: {ctx.label} repo at {dest} has uncommitted changes. "
        f"Commit or stash them before running arch-init."
    )


def _resolve_existing_clone(
    ctx: git_remote.BootstrapContext,
    *,
    allow_dirty_git_repo: bool,
    allow_dirty_uncommitted_git_repo: bool,
) -> None:
    """Validate — and, when it has no commits yet, reconcile — an existing checkout."""
    dest = ctx.dest
    if not _is_git_repo(dest):
        raise SystemExit(f"ERROR: {ctx.label} path exists but is not a git repo: {dest}")
    actual_branch = _current_branch(dest)
    if not _has_commits(dest):
        git_remote.reconcile_empty_checkout(ctx)
        actual_branch = _current_branch(dest)
    if actual_branch != ctx.branch:
        raise SystemExit(
            f"ERROR: {ctx.label} repo at {dest} is on branch '{actual_branch}', "
            f"expected '{ctx.branch}'. Switch branch manually or remove the directory."
        )
    if _has_commits(dest):
        git_remote.validate_tracking(ctx)
    _verify_working_tree(
        ctx,
        allow_dirty_git_repo=allow_dirty_git_repo,
        allow_dirty_uncommitted_git_repo=allow_dirty_uncommitted_git_repo,
    )


def _resolve_repo(
    label: str,
    spec: dict,
    workspace_root: Path,
    *,
    allow_dirty_git_repo: bool = False,
    allow_dirty_uncommitted_git_repo: bool = False,
    initialize_if_empty: bool = False,
    git_env: dict[str, str] | None = None,
) -> Path:
    """Resolve a repo spec to an absolute path, cloning if needed."""
    if "local" in spec:
        local = Path(spec["local"])
        resolved = local if local.is_absolute() else workspace_root / local
        if not resolved.is_dir():
            raise SystemExit(f"ERROR: {label} local path does not exist: {resolved}")
        if not all_model_roots(resolved):
            raise SystemExit(
                f"ERROR: {label} path has no model content — expected {MODEL}/ or "
                f"{PROJECTS}/<slug>/{MODEL}/: {resolved}"
            )
        return resolved.resolve()

    if "git" in spec:
        git = spec["git"]
        url = git.get("url")
        branch = str(git.get("branch", "main"))
        clone_path = git.get("path")
        if not url:
            raise SystemExit(f"ERROR: {label}.git.url is required")
        if not clone_path:
            raise SystemExit(f"ERROR: {label}.git.path is required")
        dest = Path(clone_path)
        if not dest.is_absolute():
            dest = workspace_root / dest
        dest = dest.resolve()

        ctx = git_remote.BootstrapContext(
            label=label,
            url=str(url),
            branch=branch,
            dest=dest,
            initialize_if_empty=initialize_if_empty,
            env=git_env,
            author_name=repo_init_commit_author_name(label),
            author_email=repo_init_commit_author_email(label),
        )

        if dest.is_dir():
            _resolve_existing_clone(
                ctx,
                allow_dirty_git_repo=allow_dirty_git_repo,
                allow_dirty_uncommitted_git_repo=allow_dirty_uncommitted_git_repo,
            )
        else:
            git_remote.bootstrap_absent(ctx)

        if not all_model_roots(dest):
            if not initialize_if_empty:
                raise SystemExit(
                    f"ERROR: {label} remote {url} has no model content ({MODEL}/ or "
                    f"{PROJECTS}/<slug>/{MODEL}/) and is not an architecture "
                    f"repository. Re-run with --initialize-{label}-repo-if-empty to scaffold and publish one."
                )
            git_remote.scaffold_in_place_and_publish(ctx)
        return dest

    raise SystemExit(f"ERROR: {label} must specify either 'local' or 'git'")


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------


class InitState(TypedDict):
    workspace_root: str
    engagement_root: str
    enterprise_root: str
    initialized_at: str


def load_init_state(start: Path | None = None) -> InitState | None:
    """Return the persisted arch-init state for the current workspace, if any."""
    state = _load_workspace_state(start)
    if not isinstance(state, dict):
        return None
    workspace_root = state.get("workspace_root")
    engagement_root = state.get("engagement_root")
    enterprise_root = state.get("enterprise_root")
    initialized_at = state.get("initialized_at")
    if not isinstance(workspace_root, str):
        return None
    if not isinstance(engagement_root, str):
        return None
    if not isinstance(enterprise_root, str):
        return None
    if not isinstance(initialized_at, str):
        return None
    return InitState(
        workspace_root=workspace_root,
        engagement_root=engagement_root,
        enterprise_root=enterprise_root,
        initialized_at=initialized_at,
    )


def _write_state(
    workspace_root: Path,
    engagement_root: Path,
    enterprise_root: Path,
) -> Path:
    state_dir = workspace_root / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / STATE_FILENAME
    state = {
        "workspace_root": str(workspace_root),
        "engagement_root": str(engagement_root),
        "enterprise_root": str(enterprise_root),
        "initialized_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(state_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(state, fh, default_flow_style=False)
    return state_path


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _collect_init_credentials(cfg: dict) -> dict[str, str] | None:
    """Probe remote URLs from the workspace config; prompt interactively for any needed credentials."""
    from src.infrastructure.git.git_auth import build_git_env, collect_credentials, create_askpass_script

    urls = [url for key in ("engagement", "enterprise") if (url := cfg.get(key, {}).get("git", {}).get("url"))]
    if not urls:
        return None
    creds = collect_credentials(urls)  # type: ignore[arg-type]
    return build_git_env(creds, create_askpass_script()) if creds else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="arch-init",
        description="Initialize architecture workspace from arch-workspace.yaml",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to arch-workspace.yaml (default: search from CWD upward)",
    )
    parser.add_argument(
        "--initialize-engagement-repo-if-empty",
        action="store_true",
        default=False,
        help="Initialize an existing empty git engagement repo if the configured branch does not exist yet",
    )
    parser.add_argument(
        "--initialize-enterprise-repo-if-empty",
        action="store_true",
        default=False,
        help="Initialize an existing empty git enterprise repo if the configured branch does not exist yet",
    )
    parser.add_argument(
        "--git-token-file",
        default=None,
        metavar="PATH",
        help="Read the HTTPS personal access token from this file (alternative to "
        "ARCH_GIT_HTTPS_TOKEN; keeps the secret out of the environment)",
    )
    parser.add_argument(
        "--repair-arch-repo",
        action="store_true",
        default=False,
        help="Bring existing repos' .arch-repo up to current defaults (base doc-types, "
        "schemata, config); migrates legacy flat schema files. Idempotent; never overwrites.",
    )
    args = parser.parse_args(argv)

    from src.infrastructure.git.git_auth import register_token_file

    register_token_file(args.git_token_file)

    if args.config:
        config_path = args.config.resolve()
        if not config_path.is_file():
            raise SystemExit(f"ERROR: config not found: {config_path}")
    else:
        config_path = _find_config(Path.cwd())
        if config_path is None:
            raise SystemExit(f"ERROR: {CONFIG_FILENAME} not found in current directory or parents")

    workspace_root = config_path.parent
    print(f"arch-init: using {config_path}")
    print(f"  workspace root: {workspace_root}")

    cfg = _parse_config(config_path)

    git_env = _collect_init_credentials(cfg)

    engagement_root = _resolve_repo(
        "engagement",
        cfg["engagement"],
        workspace_root,
        initialize_if_empty=args.initialize_engagement_repo_if_empty,
        git_env=git_env,
    )
    enterprise_root = _resolve_repo(
        "enterprise",
        cfg["enterprise"],
        workspace_root,
        initialize_if_empty=args.initialize_enterprise_repo_if_empty,
        git_env=git_env,
    )

    if args.repair_arch_repo:
        from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults  # noqa: PLC0415
        for role, root in (("engagement", engagement_root), ("enterprise", enterprise_root)):
            summary = ensure_arch_repo_defaults(root)
            changes = {k: v for k, v in summary.items() if v}
            print(f"  repair {role} ({root}): {changes or 'already current'}")

    state_path = _write_state(workspace_root, engagement_root, enterprise_root)

    # Regenerate static ArchiMate include files for both repos
    try:
        from src.infrastructure.rendering.generate_static_includes import generate_static_includes  # noqa: PLC0415
        for root in (engagement_root, enterprise_root):
            generate_static_includes(root)
        print("  static includes: regenerated")
    except Exception as exc:  # noqa: BLE001
        print(f"  static includes: skipped ({exc})")

    print("\narch-init: success")
    print(f"  engagement: {engagement_root}")
    print(f"  enterprise: {enterprise_root}")
    print(f"  state file: {state_path}")


if __name__ == "__main__":
    main()
