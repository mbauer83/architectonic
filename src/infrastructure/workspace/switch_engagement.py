"""CLI for switching the active engagement repository in arch-workspace.yaml."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from src.config.repo_paths import ENGAGEMENT_REPO, MODEL
from src.config.settings import (
    repo_init_commit_author_email,
    repo_init_commit_author_name,
    repo_init_default_branch,
)
from src.config.workspace_paths import (
    CONFIG_FILENAME,
    active_engagement_name,
    configured_engagements,
    parse_workspace_config,
)
from src.infrastructure.backend.backend_control import backend_status, ensure_backend_running, stop_backend
from src.infrastructure.backend.backend_probe import resolve_backend_port
from src.infrastructure.workspace.engagement_repo_template import create_engagement_repo
from src.infrastructure.workspace.workspace_init import (
    _find_config,
    _resolve_repo,
    _write_state,
)


def _project_directory() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_raw_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: {path} must be a YAML mapping")
    return data


def _infer_engagement_name(spec: dict) -> str:
    if "local" in spec:
        parts = Path(str(spec["local"])).parts
        if len(parts) >= 2 and parts[-1] == ENGAGEMENT_REPO:
            return parts[-2]
        if parts:
            return parts[-1]
    git_spec = spec.get("git")
    if isinstance(git_spec, dict):
        clone_path = git_spec.get("path")
        if isinstance(clone_path, str) and clone_path.strip():
            return Path(clone_path).name
        url = git_spec.get("url")
        if isinstance(url, str) and url.strip():
            return Path(url.rstrip("/")).stem.removesuffix(".git")
    return "default"


def _relative_to_workspace(path: Path, workspace_root: Path) -> str:
    return os.path.relpath(path, workspace_root)


def _repo_spec_path(spec: dict, workspace_root: Path) -> Path | None:
    if "local" in spec:
        path = Path(str(spec["local"]))
        return path if path.is_absolute() else (workspace_root / path).resolve()
    git_spec = spec.get("git")
    if isinstance(git_spec, dict):
        clone_path = git_spec.get("path")
        if isinstance(clone_path, str) and clone_path.strip():
            path = Path(clone_path)
            return path if path.is_absolute() else (workspace_root / path).resolve()
    return None


def _repo_looks_valid(path: Path) -> bool:
    return path.is_dir() and (path / MODEL).is_dir()


def _default_clone_path(name: str, workspace_root: Path, current_spec: dict | None) -> str:
    current_path = _repo_spec_path(current_spec or {}, workspace_root)
    if current_path is not None:
        if current_path.name == ENGAGEMENT_REPO and current_path.parent != current_path:
            return _relative_to_workspace(current_path.parent.parent / name / ENGAGEMENT_REPO, workspace_root)
        return _relative_to_workspace(current_path.parent / name, workspace_root)
    return _relative_to_workspace(workspace_root / "engagements" / name / ENGAGEMENT_REPO, workspace_root)


def _canonical_engagement_repo_path(name: str, workspace_root: Path) -> Path:
    return (workspace_root / "engagements" / name / ENGAGEMENT_REPO).resolve()


def _repair_existing_spec_path(name: str, spec: dict, workspace_root: Path) -> dict:
    current_path = _repo_spec_path(spec, workspace_root)
    if current_path is not None and current_path.exists():
        return spec

    canonical_path = _canonical_engagement_repo_path(name, workspace_root)
    if not _repo_looks_valid(canonical_path):
        return spec

    repaired = dict(spec)
    if "local" in repaired:
        repaired["local"] = _relative_to_workspace(canonical_path, workspace_root)
    else:
        git_spec = dict(repaired["git"])
        git_spec["path"] = _relative_to_workspace(canonical_path, workspace_root)
        repaired["git"] = git_spec
    print(f"  engagement: repaired stale path for {name} → {canonical_path}")
    return repaired


def _build_repo_spec(
    args: argparse.Namespace,
    workspace_root: Path,
    *,
    existing: dict | None,
    current_spec: dict | None,
) -> dict:
    branch = args.branch or repo_init_default_branch("engagement")
    if args.local:
        local_path = Path(args.local)
        if not local_path.is_absolute():
            local_path = (workspace_root / local_path).resolve()
        return {"local": _relative_to_workspace(local_path, workspace_root)}

    if args.url:
        clone_path = args.path or _default_clone_path(args.name, workspace_root, current_spec)
        return {
            "git": {
                "url": args.url,
                "branch": branch,
                "path": clone_path,
            }
        }

    if existing is None:
        raise SystemExit(f"ERROR: engagement '{args.name}' is not configured. Pass --url or --local to add it.")
    if not args.create:
        return _repair_existing_spec_path(args.name, existing, workspace_root)
    return existing


def _ensure_engagement_catalog(raw_config: dict) -> tuple[dict, str]:
    engagements = raw_config.get("engagements")
    if isinstance(engagements, dict):
        active = active_engagement_name(raw_config)
        if active is None:
            raise SystemExit(
                "ERROR: arch-workspace.yaml key 'engagements.active' is required when 'engagements' exists"
            )
        configured_engagements(raw_config)
        raw_available = engagements.get("available")
        if not isinstance(raw_available, dict):
            raise SystemExit("ERROR: arch-workspace.yaml key 'engagements.available' must be a YAML mapping")
        return raw_available, active

    legacy = raw_config.get("engagement")
    if not isinstance(legacy, dict):
        raise SystemExit("ERROR: arch-workspace.yaml must define 'engagement' or 'engagements'")
    inferred_name = _infer_engagement_name(legacy)
    raw_config["engagements"] = {
        "active": inferred_name,
        "available": {
            inferred_name: legacy,
        },
    }
    return raw_config["engagements"]["available"], inferred_name


def _write_config(path: Path, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, default_flow_style=False, sort_keys=False)


def _materialize_new_repo(*, spec: dict, workspace_root: Path, create: bool, branch: str) -> None:
    if not create:
        return
    if "local" in spec:
        local_path = Path(str(spec["local"]))
        target = local_path if local_path.is_absolute() else (workspace_root / local_path).resolve()
        create_engagement_repo(
            target,
            branch=branch,
            commit_author_name=repo_init_commit_author_name("engagement"),
            commit_author_email=repo_init_commit_author_email("engagement"),
        )
        return

    git_spec = spec["git"]
    clone_path = Path(str(git_spec["path"]))
    target = clone_path if clone_path.is_absolute() else (workspace_root / clone_path).resolve()
    create_engagement_repo(
        target,
        git_url=str(git_spec["url"]),
        branch=branch,
        commit_author_name=repo_init_commit_author_name("engagement"),
        commit_author_email=repo_init_commit_author_email("engagement"),
    )


def _restart_backend_if_needed(*, workspace_root: Path, enabled: bool) -> None:
    if not enabled:
        return

    port = resolve_backend_port(start=workspace_root)
    status = backend_status(cwd=workspace_root, port=port)
    reason = status.get("reason")
    should_restart = bool(status.get("running")) or reason in {"stopped_backend", "unhealthy_backend", "ok"}
    if not should_restart:
        if reason in {"unmanaged_backend", "port_in_use"}:
            print(
                "backend was not restarted automatically because the configured port is owned by a process "
                "that is not managed by this workspace"
            )
        return

    stop_result = stop_backend(cwd=workspace_root, port=port)
    if not stop_result.get("stopped") and stop_result.get("reason") not in {"not_running", "stale_pid"}:
        raise SystemExit(f"ERROR: failed to stop backend for workspace: {stop_result}")

    ensure_backend_running(
        port=port,
        cwd=workspace_root,
        project_dir=_project_directory(),
    )
    print(f"backend restarted on port {port}")


def _list_engagements(config_path: Path) -> None:
    config = parse_workspace_config(config_path)
    active = active_engagement_name(config)
    available = configured_engagements(config)
    if not available:
        only = config["engagement"]
        inferred = _infer_engagement_name(only)
        available = {inferred: only}
        active = inferred
    for name, spec in available.items():
        marker = "*" if name == active else " "
        location = spec["local"] if "local" in spec else spec["git"]["path"]
        print(f"{marker} {name}: {location}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="arch-switch-engagement",
        description="Switch the active engagement repository in arch-workspace.yaml",
    )
    parser.add_argument("name", nargs="?", help="Configured engagement name to activate")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to arch-workspace.yaml (default: search from CWD upward)",
    )
    parser.add_argument("--url", default=None, help="Git URL for a new or updated engagement repo")
    parser.add_argument(
        "--branch",
        default=None,
        help="Git branch to use for created or cloned engagement repos (default: settings.yaml repo_init)",
    )
    parser.add_argument("--path", default=None, help="Clone path relative to the workspace root when --url is used")
    parser.add_argument("--local", default=None, help="Local path for a new or updated engagement repo")
    parser.add_argument(
        "--create",
        action="store_true",
        default=False,
        help="Create and scaffold the engagement repo locally instead of requiring it to exist already",
    )
    parser.add_argument("--list", action="store_true", default=False, help="List configured engagements")
    parser.add_argument(
        "--no-restart-backend",
        action="store_true",
        default=False,
        help="Update workspace state without restarting a running backend",
    )
    args = parser.parse_args(argv)

    if args.config:
        config_path = args.config.resolve()
        if not config_path.is_file():
            raise SystemExit(f"ERROR: config not found: {config_path}")
    else:
        config_path = _find_config(Path.cwd())
        if config_path is None:
            raise SystemExit(f"ERROR: {CONFIG_FILENAME} not found in current directory or parents")

    if args.list:
        _list_engagements(config_path)
        return

    if not args.name:
        parser.error("the following arguments are required: name")
    if args.url and args.local:
        parser.error("use either --url or --local, not both")

    workspace_root = config_path.parent.resolve()
    raw_config = _load_raw_config(config_path)
    available, current_active = _ensure_engagement_catalog(raw_config)
    current_spec = available.get(current_active)
    existing = available.get(args.name)
    target_spec = _build_repo_spec(args, workspace_root, existing=existing, current_spec=current_spec)
    branch = args.branch or repo_init_default_branch("engagement")
    available[args.name] = target_spec
    raw_config["engagements"]["active"] = args.name
    # Catalog form is the single source of truth: the active entry under
    # 'engagements' fully determines the engagement, so a top-level 'engagement'
    # would be a redundant (and conflict-prone) duplicate. parse_workspace_config
    # derives it from 'engagements.active'.
    raw_config.pop("engagement", None)

    _write_config(config_path, raw_config)
    _materialize_new_repo(spec=target_spec, workspace_root=workspace_root, create=args.create, branch=branch)
    normalized = parse_workspace_config(config_path)
    engagement_root = _resolve_repo(
        "engagement",
        normalized["engagement"],
        workspace_root,
        allow_dirty_uncommitted_git_repo=args.create and "git" in normalized["engagement"],
    )
    enterprise_root = _resolve_repo(
        "enterprise",
        normalized["enterprise"],
        workspace_root,
        allow_dirty_git_repo=True,
    )
    state_path = _write_state(workspace_root, engagement_root, enterprise_root)

    _restart_backend_if_needed(workspace_root=workspace_root, enabled=not args.no_restart_backend)

    print(f"switched engagement from {current_active} to {args.name}")
    print(f"  engagement: {engagement_root}")
    print(f"  enterprise: {enterprise_root}")
    print(f"  state file: {state_path}")


if __name__ == "__main__":
    main()
