"""Entity deletion operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry
from src.domain.artifact_id import stable_id

from .boundary import assert_engagement_write_root
from .types import WriteResult


def _verification(path: Path, *, valid: bool, issues: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "entity",
        "valid": valid,
        "issues": issues or [],
    }


def _owned_outgoing_path(entity_file: Path) -> Path:
    return entity_file.with_suffix(".outgoing.md")


def _owned_connection_ids(registry: ArtifactRegistry, artifact_id: str) -> list[str]:
    ids: list[str] = []
    for conn in registry.find_connections_for(artifact_id, direction="outbound"):
        ids.append(f"{conn.source}---{conn.target}@@{conn.conn_type}")
        ids.append(f"{conn.source} {conn.conn_type} → {conn.target}")
    return ids


def _format_dependency_tree(
    artifact_id: str,
    *,
    incoming_connections: list[str],
    diagram_refs: list[str],
    grf_refs: list[str],
) -> str:
    lines = [artifact_id]
    if incoming_connections:
        lines.append("  incoming-connections")
        lines.extend(f"    {item}" for item in incoming_connections)
    if diagram_refs:
        lines.append("  diagrams")
        lines.extend(f"    {item}" for item in diagram_refs)
    if grf_refs:
        lines.append("  global-entity-references")
        lines.extend(f"    {item}" for item in grf_refs)
    return "\n".join(lines)


def _incoming_connection_blockers(registry: ArtifactRegistry, artifact_id: str) -> list[str]:
    """Connections from other entities that target *artifact_id*."""
    blockers: list[str] = []
    for conn in registry.find_connections_for(artifact_id, direction="inbound"):
        if stable_id(conn.source) == stable_id(artifact_id):
            continue
        blockers.append(f"{conn.source} {conn.conn_type} → {artifact_id}")
    return blockers


def _grf_blockers(registry: ArtifactRegistry, artifact_id: str, entity_file: Path) -> list[str]:
    """Internal global-artifact-reference proxies pointing at *artifact_id*."""
    return [
        rec.artifact_id
        for rec in registry.grf_references_to_entity(artifact_id)
        if rec.path.resolve() != entity_file.resolve()
    ]


def _diagram_blockers(registry: ArtifactRegistry, artifact_id: str, owned_connection_ids: set[str]) -> list[str]:
    """Diagrams referencing the entity or any connection it owns."""
    diagram_ids = {rec.artifact_id for rec in registry.diagrams_referencing_artifact(artifact_id)}
    for conn_id in owned_connection_ids:
        diagram_ids.update(rec.artifact_id for rec in registry.diagrams_referencing_artifact(conn_id))
    return sorted(diagram_ids)


def _entity_ref_blockers(
    *,
    registry: ArtifactRegistry,
    artifact_id: str,
    entity_file: Path,
    owned_connection_ids: set[str],
    ignore_diagram_refs: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    incoming_connections = _incoming_connection_blockers(registry, artifact_id)
    grf_refs = _grf_blockers(registry, artifact_id, entity_file)
    diagram_refs = [] if ignore_diagram_refs else _diagram_blockers(registry, artifact_id, owned_connection_ids)
    return incoming_connections, diagram_refs, grf_refs


def _delete_entity_core(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    ignore_diagram_refs: bool = False,
    dry_run: bool,
) -> WriteResult:
    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        raise ValueError(f"Entity '{artifact_id}' not found in model")
    resolved = registry.resolve_artifact(artifact_id)
    if resolved is not None:
        artifact_id = resolved.canonical_id
    try:
        entity_file.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"Entity '{artifact_id}' is not in writable repo '{repo_root}'") from exc

    outgoing_path = _owned_outgoing_path(entity_file)
    owned_connection_ids = set(_owned_connection_ids(registry, artifact_id))
    incoming_connections, diagram_refs, grf_refs = _entity_ref_blockers(
        registry=registry,
        artifact_id=artifact_id,
        entity_file=entity_file,
        owned_connection_ids=owned_connection_ids,
        ignore_diagram_refs=ignore_diagram_refs,
    )
    if incoming_connections or diagram_refs or grf_refs:
        tree = _format_dependency_tree(
            artifact_id,
            incoming_connections=incoming_connections,
            diagram_refs=diagram_refs,
            grf_refs=grf_refs,
        )
        raise ValueError(
            f"Cannot delete entity '{artifact_id}' because it is still referenced.\n"
            "Delete or update these dependents first:\n"
            f"{tree}"
        )

    warnings: list[str] = []
    if outgoing_path.exists():
        warnings.append(f"Will delete owned outgoing file: {outgoing_path.name}")

    if dry_run:
        preview = "\n".join(
            [
                f"Would delete entity: {entity_file}",
                *([f"Would delete outgoing file: {outgoing_path}"] if outgoing_path.exists() else []),
            ]
        )
        return WriteResult(
            wrote=False,
            path=entity_file,
            artifact_id=artifact_id,
            content=preview,
            warnings=warnings,
            verification=_verification(entity_file, valid=True),
        )

    entity_file.unlink(missing_ok=False)
    deleted_paths: list[Path] = [entity_file]
    if outgoing_path.exists():
        outgoing_path.unlink()
        deleted_paths.append(outgoing_path)

    for changed_path in deleted_paths:
        clear_repo_caches(changed_path)
    return WriteResult(
        wrote=True,
        path=entity_file,
        artifact_id=artifact_id,
        content=None,
        warnings=warnings,
        verification=_verification(entity_file, valid=True),
    )


def delete_entity(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    ignore_diagram_refs: bool = False,
    dry_run: bool,
) -> WriteResult:
    assert_engagement_write_root(repo_root)
    return _delete_entity_core(
        repo_root=repo_root,
        registry=registry,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        ignore_diagram_refs=ignore_diagram_refs,
        dry_run=dry_run,
    )
