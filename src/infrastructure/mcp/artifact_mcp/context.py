"""context.py — shared MCP server context for model query/verify/write tools.

Shared context helpers for the artifact MCP servers by factoring out:
- repo root resolution
- cache keys and cached ArtifactRepository/ArtifactRegistry
- verifier construction and cache clearing

This module contains no FastMCP tool registrations.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from src.application.artifact_query import ArtifactRepository
from src.application.read_models import ReadModelVersion
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.config.repo_paths import MODEL
from src.config.workspace_paths import resolve_workspace_repo_roots
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.artifact_index.coordination import (
    publish_authoritative_mutation,
    publish_background_refresh_completed,
    wait_for_write_queue_drain,
)
from src.infrastructure.mcp.artifact_mcp._background_refresh_queue import (
    REFRESH_DEBOUNCE_S,
    queue_for,
    refresh_worker,
)
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

RepoPreset = Literal[
    "engagement",
    "enterprise",
]

RepoScope = Literal["engagement", "enterprise", "both"]


def expand_artifact_id(registry_or_repo, artifact_id: str) -> str:
    """Expand a short or stale-slug entity ID to the current canonical full ID.

    Connection IDs (containing '---') are returned unchanged — they are already
    stable (slug-free endpoints) after the WS6 canonical-key migration.
    """
    from src.domain.artifact_id import stable_id as _stable_id  # noqa: PLC0415

    if "---" in artifact_id:
        return artifact_id
    short = _stable_id(artifact_id)
    for candidate in registry_or_repo.entity_ids():
        if _stable_id(candidate) == short:
            return candidate
    return artifact_id


def workspace_root() -> Path:
    # .../src/infrastructure/mcp/artifact_mcp/context.py ->
    # parents[0]=artifact_mcp, [1]=mcp, [2]=infrastructure, [3]=src, [4]=repo root
    return Path(__file__).resolve().parents[4]


def _workspace_repo_roots() -> tuple[Path, Path] | None:
    return resolve_workspace_repo_roots(workspace_root())


def _configured_repo_root(*names: str) -> Path | None:
    import os

    value = next((os.getenv(name) for name in names if os.getenv(name)), None)
    return Path(value).expanduser() if value is not None else None


def default_engagement_repo_root() -> Path:
    configured = _configured_repo_root("ARCH_MCP_MODEL_REPO_ROOT", "ARCH_REPO_ROOT")
    if configured is not None:
        return configured
    roots = _workspace_repo_roots()
    if roots is None:
        raise RuntimeError(
            "Could not resolve engagement repo root. "
            "Run `arch-init` or provide arch-workspace.yaml / ARCH_MCP_MODEL_REPO_ROOT."
        )
    return roots[0]


def default_enterprise_repo_root() -> Path:
    configured = _configured_repo_root("ARCH_ENTERPRISE_ROOT")
    if configured is not None:
        return configured
    roots = _workspace_repo_roots()
    if roots is None:
        raise RuntimeError("Could not resolve enterprise repo root. Run `arch-init` or provide arch-workspace.yaml.")
    return roots[1]


def repo_root_from_preset(preset: RepoPreset) -> Path:
    roots = _workspace_repo_roots()
    if roots is None:
        raise RuntimeError(
            "Could not resolve workspace repo roots for repo_preset. Run `arch-init` or provide arch-workspace.yaml."
        )
    match preset:
        case "engagement":
            return roots[0]
        case "enterprise":
            return roots[1]


def _absolutized(p: Path) -> Path:
    return p if p.is_absolute() else workspace_root() / p


def resolve_repo_root(*, repo_root: str | None, repo_preset: RepoPreset | None) -> Path:
    if repo_root:
        return _absolutized(Path(repo_root).expanduser())
    if repo_preset:
        return repo_root_from_preset(repo_preset)
    return _absolutized(default_engagement_repo_root())


def resolve_enterprise_repo_root(*, enterprise_root: str | None) -> Path:
    if enterprise_root:
        return _absolutized(Path(enterprise_root).expanduser())
    return default_enterprise_repo_root()


def resolve_repo_roots(
    *,
    repo_scope: RepoScope,
    repo_root: str | None,
    repo_preset: RepoPreset | None,
    enterprise_root: str | None,
) -> list[Path]:
    engagement = resolve_repo_root(repo_root=repo_root, repo_preset=repo_preset)
    enterprise = resolve_enterprise_repo_root(enterprise_root=enterprise_root)
    roots: list[Path] = []
    if repo_scope in ("engagement", "both"):
        roots.append(engagement)
    if repo_scope in ("enterprise", "both"):
        roots.append(enterprise)
    return roots


def roots_key(roots: list[Path]) -> str:
    return "|".join(str(p.resolve()) for p in roots)


def _shared_state_repo_for_roots(roots: list[Path]) -> ArtifactRepository | None:
    try:
        from src.infrastructure.gui.routers import state as gui_state
    except Exception:  # noqa: BLE001
        return None

    repo = gui_state.maybe_get_repo()
    if repo is None:
        return None
    configured = gui_state.configured_roots()
    wanted = [p.resolve() for p in roots]
    if configured == wanted:
        return repo
    return None


@lru_cache(maxsize=1)
def runtime_catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


@lru_cache(maxsize=8)
def repo_cached(roots_key_str: str) -> ArtifactRepository:
    roots = [Path(p) for p in roots_key_str.split("|") if p]
    shared = _shared_state_repo_for_roots(roots)
    if shared is not None:
        return shared
    return ArtifactRepository(
        shared_artifact_index(roots),
        excluded_entity_types=runtime_catalogs().ontology.entity_types_with_class("internal"),
    )


@lru_cache(maxsize=8)
def registry_cached(roots_key_str: str) -> ArtifactRegistry:
    roots = [Path(p) for p in roots_key_str.split("|") if p]
    return ArtifactRegistry(shared_artifact_index(roots))


def verifier_for(roots_key_str: str, *, include_registry: bool) -> ArtifactVerifier:
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    catalogs = build_runtime_catalogs(get_module_registry())
    # The committed CandidateRepository lets datatype type-reference resolution (E332) see
    # classifiers defined in other diagrams; same-diagram references are resolved by the
    # projection from the diagram under verification (compile_projection's same-write step).
    committed_repo = committed_repository(repo_cached(roots_key_str))
    registry = registry_cached(roots_key_str) if include_registry else None
    return build_artifact_verifier(registry, catalogs=catalogs, committed_repo=committed_repo)


def _refresh_repo_now(roots: list[Path]) -> ReadModelVersion:
    # Operate directly on the shared index — the ArtifactRepository is a thin
    # wrapper and both would resolve to the same ArtifactIndex instance, so
    # calling through both used to trigger two full refreshes under the lock.
    index = shared_artifact_index(roots)
    index.refresh()
    registry_cached.cache_clear()
    return index.read_model_version()


def _apply_paths_now(roots: list[Path], paths: list[Path]) -> ReadModelVersion:
    # Broadcasting via notify_paths_changed (not calling index.apply_file_changes directly)
    # is load-bearing: `roots` reflects only *this* caller's scope (e.g. engagement-only for
    # edit_tools.py), but other live cached ArtifactIndex singletons for overlapping physical
    # repos (e.g. the engagement+enterprise-combined index the REST/GUI layer holds) must see
    # this write too, or they silently serve a stale existence check until a manual reindex —
    # notify_paths_changed already applies changes to every registered index whose mounts
    # overlap the given paths (see bootstrap.py), so it is the correct universal write-commit
    # hook, not just the git-sync hook it also used to look like.
    index = shared_artifact_index(roots)  # ensures this scope's index exists/is registered
    notify_paths_changed(paths)
    registry_cached.cache_clear()
    return index.read_model_version()



def _normalize_roots(root_or_roots: Path | list[Path]) -> list[Path]:
    roots = root_or_roots if isinstance(root_or_roots, list) else [root_or_roots]
    return [root.resolve() for root in roots]


def _infer_repo_roots_from_paths(paths: list[Path]) -> list[Path]:
    inferred: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        for candidate in (resolved, *resolved.parents):
            if (candidate / MODEL).is_dir():
                root = candidate.resolve()
                if root not in seen:
                    inferred.append(root)
                    seen.add(root)
                break
    return inferred


def apply_authoritative_changes(changed_paths: list[Path], repo_roots: list[Path]) -> ReadModelVersion | None:
    if not changed_paths:
        return None
    roots = _normalize_roots(repo_roots)
    paths = [path.resolve() for path in changed_paths]
    version = _apply_paths_now(roots, paths)
    publish_authoritative_mutation(roots, changed_paths=paths, version=version)
    return version


def enqueue_background_refresh(
    repo_roots: list[Path],
    *,
    changed_paths: list[Path] | None = None,
    full_refresh: bool,
) -> None:
    roots = _normalize_roots(repo_roots)
    queue = queue_for(roots_key(roots))
    with queue.cond:
        if full_refresh:
            queue.pending_full = True
            queue.pending_paths = set()
        elif changed_paths:
            if queue.pending_paths is None:
                queue.pending_paths = set()
            queue.pending_paths.update(path.resolve() for path in changed_paths)
        queue.next_due_monotonic = time.monotonic() + REFRESH_DEBOUNCE_S
        if queue.worker is None or not queue.worker.is_alive():
            queue.worker = threading.Thread(
                target=refresh_worker,
                args=(
                    roots, queue, _refresh_repo_now, _apply_paths_now,
                    wait_for_write_queue_drain, publish_background_refresh_completed,
                ),
                daemon=True,
                name=f"model-refresh:{roots_key(roots)}",
            )
            queue.worker.start()
        queue.cond.notify_all()


@dataclass
class AuthoritativeMutationContext:
    repo_roots: list[Path]
    changed_paths: set[Path] = field(default_factory=set)

    def record_changed(self, path: Path) -> None:
        self.changed_paths.add(path.resolve())

    def finalize(self) -> ReadModelVersion | None:
        roots = _normalize_roots(self.repo_roots)
        if not self.changed_paths:
            return None
        return apply_authoritative_changes(sorted(self.changed_paths), roots)


def mutation_context_for(
    root_or_roots: Path | list[Path],
) -> AuthoritativeMutationContext:
    return AuthoritativeMutationContext(repo_roots=_normalize_roots(root_or_roots))


def authoritative_callbacks_for(
    root_or_roots: Path | list[Path],
) -> tuple[AuthoritativeMutationContext, Callable[[Path], None]]:
    context = mutation_context_for(root_or_roots)
    return context, context.record_changed


def sync_refresh_for_roots(root_or_roots: Path | list[Path]) -> None:
    roots = _normalize_roots(root_or_roots)
    wait_for_write_queue_drain()
    version = _refresh_repo_now(roots)
    publish_background_refresh_completed(roots, full_refresh=True, changed_paths=[], version=version)


def refresh_caches_for_repo(root_or_roots: Path | list[Path]) -> None:
    sync_refresh_for_roots(root_or_roots)


def clear_caches_for_repo(root_or_roots: Path | list[Path]) -> None:
    paths = root_or_roots if isinstance(root_or_roots, list) else [root_or_roots]
    repo_roots = _infer_repo_roots_from_paths(paths)
    if not repo_roots:
        repo_roots = [path.resolve() for path in paths]
    apply_authoritative_changes(paths, repo_roots)


@dataclass(frozen=True)
class ResolvedRepo:
    roots: list[Path]

    @property
    def key(self) -> str:
        return roots_key(self.roots)

    @property
    def engagement_root(self) -> Path:
        return self.roots[0]
