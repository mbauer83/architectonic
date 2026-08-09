"""Shared server state and helper functions for GUI router modules."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import HTTPException
else:
    try:
        from fastapi import HTTPException
    except ModuleNotFoundError:  # pragma: no cover - test env without GUI deps

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str) -> None:
                self.status_code = status_code
                self.detail = detail
                super().__init__(detail)



from src.application.artifacts.query import ArtifactRepository
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    EntityRecord,
)
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import notify_paths_changed
from src.infrastructure.artifact_index.coordination import publish_authoritative_mutation
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.viewpoint_declarations import with_effective_viewpoints

# Module-level server state — set by backend.arch_backend.main() before uvicorn starts.
# Guarded by _state_lock so background threads (git sync, refresh workers) can
# safely read these values without racing against init_state().
_state_lock = threading.Lock()
_repo: ArtifactRepository | None = None
_repo_root: Path | None = None  # engagement root — used for writes
_enterprise_root: Path | None = None  # enterprise root — read-only in normal mode
_admin_mode: bool = False  # when True, enterprise writes are permitted via /admin/api/*
_read_only: bool = False  # when True, all engagement writes are blocked


def init_state(
    repo: ArtifactRepository,
    repo_root: Path,
    enterprise_root: Path | None,
    *,
    admin_mode: bool = False,
    read_only: bool = False,
) -> None:
    global _repo, _repo_root, _enterprise_root, _admin_mode, _read_only
    with _state_lock:
        _repo = repo
        _repo_root = repo_root
        _enterprise_root = enterprise_root
        _admin_mode = admin_mode
        _read_only = read_only


def is_admin_mode() -> bool:
    with _state_lock:
        return _admin_mode


def is_read_only() -> bool:
    with _state_lock:
        return _read_only


def get_repo() -> ArtifactRepository:
    with _state_lock:
        repo = _repo
    if repo is None:
        raise HTTPException(500, "Repository not initialized")
    return repo


def maybe_get_repo() -> ArtifactRepository | None:
    with _state_lock:
        return _repo


def maybe_engagement_root() -> Path | None:
    """Return the engagement repository root, or None if not initialised."""
    with _state_lock:
        return _repo_root


def maybe_enterprise_root() -> Path | None:
    """Return the enterprise repository root, or None if not configured."""
    with _state_lock:
        return _enterprise_root


def configured_roots() -> list[Path]:
    with _state_lock:
        roots: list[Path] = []
        if _repo_root is not None:
            roots.append(_repo_root.resolve())
        if _enterprise_root is not None:
            roots.append(_enterprise_root.resolve())
        return roots


def is_global(path: Path) -> bool:
    with _state_lock:
        ent = _enterprise_root
    return ent is not None and path.is_relative_to(ent)


def entity_to_summary(
    e: EntityRecord,
    conn_counts: dict[str, tuple[int, int, int]] | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "artifact_id": e.artifact_id,
        "artifact_type": e.artifact_type,
        "name": e.name,
        "version": e.version,
        "status": e.status,
        "domain": e.domain,
        "subdomain": e.subdomain,
        "path": str(e.path),
        "is_global": is_global(e.path),
        "group": e.group,
        "specializations": list(e.specializations),
        "last_updated": e.last_updated,
    }
    if e.host_diagram_id is not None:
        d["host_diagram_id"] = e.host_diagram_id
    if conn_counts is not None:
        inc, sym, out = conn_counts.get(e.artifact_id, (0, 0, 0))
        d["conn_in"] = inc
        d["conn_sym"] = sym
        d["conn_out"] = out
    return d


def build_conn_counts(repo: ArtifactRepository) -> dict[str, tuple[int, int, int]]:
    return repo.connection_counts()


def build_conn_counts_for_entities(repo: ArtifactRepository, entity_ids: list[str]) -> dict[str, tuple[int, int, int]]:
    return repo.connection_counts_for_entities(entity_ids)


def resolve_gar(artifact_id: str) -> tuple[str, bool]:
    """If artifact_id is a GAR, return (global_artifact_id, True); else (artifact_id, False)."""
    with _state_lock:
        repo = _repo
    if repo is None:
        return artifact_id, False
    rec = repo.get_entity(artifact_id)
    if rec is not None and is_internal_entity_type(rec.artifact_type, process_runtime_catalogs().ontology):
        gaid = rec.extra.get("global-artifact-id")
        if isinstance(gaid, str) and gaid:
            return gaid, True
    return artifact_id, False


def connection_to_dict(c: ConnectionRecord) -> dict[str, Any]:
    with _state_lock:
        repo = _repo
    resolved_target, via_gar = resolve_gar(c.target)
    src_name = c.source
    tgt_name = resolved_target
    if repo is not None:
        src_rec = repo.get_entity(c.source)
        tgt_rec = repo.get_entity(resolved_target)
        if src_rec is not None and src_rec.name:
            src_name = src_rec.name
        if tgt_rec is not None and tgt_rec.name:
            tgt_name = tgt_rec.name
    d: dict[str, Any] = {
        "artifact_id": c.artifact_id,
        "source": c.source,
        "target": resolved_target,
        "conn_type": c.conn_type,
        "version": c.version,
        "status": c.status,
        "path": str(c.path),
        "content_text": c.content_text,
        "associated_entities": list(c.associated_entities),
        "src_multiplicity": c.src_multiplicity,
        "tgt_multiplicity": c.tgt_multiplicity,
        "specializations": list(c.specializations),
        "metadata": dict(c.attributes),
        "source_name": src_name,
        "target_name": tgt_name,
    }
    if via_gar:
        d["gar_artifact_id"] = c.target
    return d


def diagram_to_summary(d: DiagramRecord) -> dict[str, Any]:
    return {
        "artifact_id": d.artifact_id,
        "name": d.name,
        "diagram_type": d.diagram_type,
        "version": d.version,
        "status": d.status,
        "path": str(d.path),
        "group": d.group,
        "is_global": is_global(d.path),
        "last_updated": d.last_updated,
    }


def get_write_deps(catalogs: RuntimeCatalogs) -> tuple[Path, Any, Any]:
    """Return (engagement_root, registry, verifier). Registry spans both repos.

    ``catalogs`` is a parameter, not a lookup. Every one of these twenty-nine call sites is a request
    handler, so the catalogs a test overrode through ``runtime_catalogs_dependency`` reached every
    *read* and no write at all — the write path built its own from process state, which is the shape
    of the ``E180`` defect: the process catalogue's viewpoints are the module starter library and read
    no repository, so a diagram applying a definition you had just saved failed verification
    permanently. Reloading the viewpoints here fixed that one catalogue; taking the catalogs from the
    caller is what stops the next divergence between what a handler reads and what it writes against.
    """
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

    with _state_lock:
        repo_root = _repo_root
        enterprise_root = _enterprise_root
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    index = (
        combined_artifact_index(repo_root, enterprise_root)
        if enterprise_root is not None
        else shared_artifact_index(repo_root)
    )
    registry = ArtifactRegistry(index)
    # Viewpoints reloaded for these roots, the same way every read surface resolves a slug. The
    # process catalog's viewpoints are the module-shipped starter library only, so a diagram or
    # matrix applying a repo-authored definition failed verification with `E180 Unknown viewpoint
    # slug` — permanently, not until a restart.
    effective = with_effective_viewpoints(catalogs, _write_catalog_roots(repo_root, enterprise_root))
    return repo_root, registry, build_artifact_verifier(registry, catalogs=effective)


def _write_catalog_roots(repo_root: Path | None, enterprise_root: Path | None) -> list[Path]:
    """The roots whose viewpoint declarations a write must see, engagement last.

    Merge order is tier order: an engagement definition overrides an enterprise one of the same
    slug, exactly as ``load_effective_viewpoint_catalog`` composes them for reads. Either root may
    be absent — the admin surface runs without an engagement, the ordinary one without an
    enterprise — and a deployment configuring neither is already refused before this is reached.
    """
    return [root for root in (enterprise_root, repo_root) if root is not None]


def get_admin_write_deps(catalogs: RuntimeCatalogs) -> tuple[Path, Any, Any]:
    """Return (enterprise_root, registry, verifier) for admin-mode writes.

    Raises 403 when admin mode is not enabled, 500 when enterprise root is
    not configured.  Registry spans both repos so cross-repo entity references
    in outgoing files validate correctly.
    """
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

    with _state_lock:
        admin_mode = _admin_mode
        enterprise_root = _enterprise_root
        repo_root = _repo_root
    if not admin_mode:
        raise HTTPException(403, "Admin mode is not enabled")
    if enterprise_root is None:
        raise HTTPException(500, "Enterprise repository not configured")
    index = (
        combined_artifact_index(repo_root, enterprise_root)
        if repo_root is not None
        else shared_artifact_index(enterprise_root)
    )
    registry = ArtifactRegistry(index)
    # Same reload as the engagement write path: an enterprise-tier write may apply an
    # enterprise-authored viewpoint, which the process catalog also does not hold.
    effective = with_effective_viewpoints(catalogs, _write_catalog_roots(repo_root, enterprise_root))
    return enterprise_root, registry, build_artifact_verifier(registry, catalogs=effective)


def clear_caches(path: Path | list[Path]) -> None:
    with _state_lock:
        repo = _repo
    if repo is not None:
        changed_paths = path if isinstance(path, list) else [path]
        # notify_paths_changed (not repo.apply_file_changes) updates every live cached
        # ArtifactIndex singleton whose mounts overlap these paths — not just this REST
        # layer's own engagement+enterprise-combined index. MCP write tools resolve a
        # narrower, engagement-only index for the same physical repo; without this broadcast
        # their existence checks (e.g. artifact_delete_entity) would keep serving stale state
        # for anything created/changed through the GUI until a manual admin reindex.
        notify_paths_changed(changed_paths)
        version = repo.read_model_version()
        roots = configured_roots()
        if roots:
            publish_authoritative_mutation(roots, changed_paths=changed_paths, version=version)


def refresh_now() -> None:
    with _state_lock:
        repo = _repo
    if repo is not None:
        repo.refresh()


def _refusal(code: Any, message: str) -> Any:
    """One refused write, as the client receives it.

    Both channels arrive here. The authorization policy raises ``MutationRejected`` with a typed
    denial; the workspace gate raises ``GateRejected`` with a block reason from the same vocabulary.
    They were translated separately — the policy's code used only to choose 423 over 403 and then
    discarded, the gate's reason interpolated into prose — so a client could not tell "the workspace
    is read-only" from "a sync is running" from "the remote is unreachable" without matching on
    English, and `DenialDetails.reason_code` arrived carrying a copy of the envelope's own generic
    code. Its docstring says what it is for: *a client branches on `reason_code`*.

    Retryability is asked of the vocabulary rather than decided here, so the status and the flag
    cannot disagree.
    """
    from src.application.mutation_authorization import is_retryable
    from src.infrastructure.rest.contracts.errors import ApiError, DenialDetails

    retryable = is_retryable(code)
    return ApiError(
        423 if retryable else 403,
        "write_rejected" if retryable else "forbidden",
        f"Write rejected: {message}",
        DenialDetails(reason_code=code, retryable=retryable),
    )


def authorized_write(operation_id: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Execute a repository mutation through the authorized mutation executor.

    ``operation_id`` is the handler's identity in the route-policy manifest — the only way a REST
    handler reaches the write queue and gate. An **operation id, not a path**: the path is what a
    rename changes, and a handler holding a stale path failed its write closed with nothing red in
    the suite. Denials surface with the ordinary REST write status (423 retryable, 403 forbidden).
    """
    from src.application.mutation_authorization import MutationRejected
    from src.infrastructure.rest.routers.rest_mutation_manifest import build_rest_request
    from src.infrastructure.workspace.mutation_gate import GateRejected
    from src.infrastructure.write.mutation_executor_registry import mutation_executor

    request = build_rest_request(operation_id)
    try:
        return mutation_executor().run(request, lambda: fn(*args, **kwargs), operation_name=fn.__name__)
    except MutationRejected as exc:
        raise _refusal(exc.denial.code, exc.denial.message) from exc
    except GateRejected as exc:
        raise _refusal(exc.reason, str(exc.reason)) from exc


async def authorized_write_async(operation_id: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Async variant of ``authorized_write`` for coroutine handlers: awaits the queued
    write without blocking the event loop."""
    import asyncio

    from src.application.mutation_authorization import MutationRejected
    from src.infrastructure.rest.routers.rest_mutation_manifest import build_rest_request
    from src.infrastructure.workspace.mutation_gate import GateRejected
    from src.infrastructure.write.mutation_executor_registry import mutation_executor

    request = build_rest_request(operation_id)
    try:
        future = mutation_executor().submit(request, lambda: fn(*args, **kwargs), operation_name=fn.__name__)
        return await asyncio.wrap_future(future)
    except MutationRejected as exc:
        raise _refusal(exc.denial.code, exc.denial.message) from exc
    except GateRejected as exc:
        raise _refusal(exc.reason, str(exc.reason)) from exc


def write_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "wrote": bool(result.wrote),
        "path": str(result.path),
        "artifact_id": result.artifact_id,
        "content": result.content,
        "warnings": result.warnings,
        "verification": result.verification,
    }


def get_both_roots() -> tuple[Path, Path]:
    if _repo_root is None or _enterprise_root is None:
        raise HTTPException(500, "Both engagement and enterprise repos must be initialized")
    return _repo_root, _enterprise_root
