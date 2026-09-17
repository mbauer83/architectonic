"""Which of a workspace's repositories are git-backed, and in which role.

Read from `arch-workspace.yaml` — the same document `arch-init` resolves — so every process that
needs credentials for the workspace's remotes (the serving backend, a detached start, the updater)
asks one question of one file. It used to live in the backend application module, which made anything
that wanted the answer import the whole FastAPI app to get it.
"""

from __future__ import annotations

from pathlib import Path

from src.config.workspace_paths import find_workspace_config, parse_workspace_config
from src.infrastructure.git.git_sync import RepoSpec


def configured_git_repos(start: Path | None = None) -> list[RepoSpec]:
    """The git-backed repositories the workspace found from `start` (default: the cwd) declares."""
    cfg = find_workspace_config((start or Path.cwd()).resolve())
    if cfg is None:
        return []
    workspace_root = cfg.parent
    config = parse_workspace_config(cfg)
    repos: list[RepoSpec] = []
    for key in ("engagement", "enterprise"):
        spec = config.get(key, {})
        if "git" in spec:
            git_spec = spec["git"]
            rel = git_spec.get("path", f"./{key}-repository")
            repos.append(RepoSpec(path=(workspace_root / rel).resolve(), role=key))  # type: ignore[arg-type]
    return repos
