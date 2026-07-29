"""MCP write tools: connection creation."""

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.context import expand_artifact_id
from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE
from src.infrastructure.mcp.artifact_mcp.write._common import (
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)


def _add_connection_impl(
    *,
    source_entity: str,
    connection_type: str,
    target_entity: str,
    description: str | None,
    src_multiplicity: str | None,
    tgt_multiplicity: str | None,
    version: str,
    status: str,
    dry_run: bool,
    repo_root: str | None,
    provisional_ids: frozenset[str],
    clear_repo_caches=None,
    specialization: str | None = None,
    specializations: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Internal implementation shared by the MCP tool and bulk_write."""
    scope: Literal["engagement", "both"] = "engagement" if repo_root else "both"
    both_roots = resolve_repo_roots(
        repo_scope=scope,
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    both_key = roots_key(both_roots)
    registry = registry_cached(both_key)
    verifier = verifier_for(both_key, include_registry=True)
    eng_root = both_roots[0]
    if clear_repo_caches is None:
        # Notification scope must match the scope validation ran against (both_roots) — an
        # engagement-only mutation context here previously left the combined-scope index this
        # call just validated against un-notified of its own write.
        _context, clear_repo_caches = authoritative_callbacks_for(both_roots)

    source_entity = expand_artifact_id(registry, source_entity)
    target_entity = expand_artifact_id(registry, target_entity)
    effective_source = source_entity
    effective_target = target_entity
    gar_source_id: str | None = None
    gar_artifact_id: str | None = None
    warnings: list[str] = []

    def _ensure_gar(global_id: str) -> str:
        nonlocal registry, verifier
        from src.infrastructure.write.artifact_write.global_artifact_reference import (
            ensure_global_artifact_reference,
        )

        full_repo = repo_cached(both_key)
        rec = full_repo.get_entity(global_id)
        name = rec.name if rec else global_id
        entity_type = rec.artifact_type if rec else None
        eng_repo = repo_cached(roots_key(both_roots[:1]))
        gar_result = ensure_global_artifact_reference(
            engagement_repo=eng_repo,
            engagement_root=eng_root,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            global_artifact_id=global_id,
            global_artifact_name=name,
            global_artifact_type="entity",
            global_artifact_entity_type=entity_type,
            dry_run=dry_run,
        )
        if gar_result.wrote:
            warnings.append(f"Created GAR proxy {gar_result.artifact_id} for {global_id}")
        else:
            warnings.append(f"Routed via existing GAR proxy {gar_result.artifact_id}")
        full_repo.refresh()
        eng_repo.refresh()
        registry.refresh()
        verifier = verifier_for(both_key, include_registry=True)
        return gar_result.artifact_id

    if source_entity in registry.enterprise_entity_ids():
        gar_source_id = _ensure_gar(source_entity)
        effective_source = gar_source_id

    if target_entity in registry.enterprise_entity_ids():
        gar_artifact_id = _ensure_gar(target_entity)
        effective_target = gar_artifact_id

    result = artifact_write_ops.add_connection(
        repo_root=eng_root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        source_entity=effective_source,
        connection_type=connection_type,
        target_entity=effective_target,
        description=description,
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
        specialization=specialization,
        specializations=specializations,
        metadata=metadata,
        version=version,
        status=status,
        last_updated=None,
        dry_run=dry_run,
        extra_known_ids=provisional_ids,
    )
    out = _out(result, dry_run=dry_run)
    if gar_source_id:
        out["gar_source_id"] = gar_source_id
        out["original_source"] = source_entity
    if gar_artifact_id:
        out["gar_artifact_id"] = gar_artifact_id
        out["original_target"] = target_entity
    all_warnings = warnings + list(result.warnings or [])
    if all_warnings:
        out["warnings"] = all_warnings
    return out


def artifact_add_connection(
    *,
    source_entity: str = "",
    connection_type: str,
    target_entity: str = "",
    description: str | None = None,
    src_multiplicity: str | None = None,
    tgt_multiplicity: str | None = None,
    specialization: str | None = None,
    specializations: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    from_diagram_element: dict[str, object] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    """Add a connection in the engagement repo.

    Defaults use repos from arch-init workspace config.
    When source_entity or target_entity is a global (enterprise) entity, a
    global-entity-reference proxy is created or reused automatically so all
    connection endpoints are represented in the engagement repo.
    from_diagram_element: {diagram_id, diagram_element_id, diagram_element_kind='connection'} —
    when provided, derives source/target from the diagram element's represents bindings and
    atomically attaches a binding to the diagram connection (materialization).
    """
    scope: Literal["engagement", "both"] = "engagement" if repo_root else "both"
    roots = resolve_repo_roots(repo_scope=scope, repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)

    if from_diagram_element and str(from_diagram_element.get("diagram_element_kind", "connection")) == "connection":
        from src.infrastructure.write.artifact_write.materialization import (  # noqa: PLC0415
            DiagramElementRef,
            materialize_connection,
        )
        ref = DiagramElementRef(
            diagram_id=str(from_diagram_element.get("diagram_id", "")),
            diagram_element_id=str(from_diagram_element.get("diagram_element_id", "")),
            diagram_element_kind="connection",
        )
        registry = registry_cached(roots_key(roots))
        verifier = verifier_for(roots_key(roots), include_registry=True)
        mat = materialize_connection(
            repo_root=roots[0], registry=registry, verifier=verifier,
            clear_repo_caches=clear_repo_caches, ref=ref,
            connection_type=connection_type, description=description,
            version=version, status=status, dry_run=dry_run,
        )
        if mat.wrote and not dry_run:
            mutation_context.finalize()
        return {
            "dry_run": dry_run,
            "wrote": mat.wrote,
            "connection_id": mat.connection_id,
            "proposed_connection_id": mat.proposed_connection_id,
            "diagram_id": mat.diagram_id,
            "diagram_element_id": mat.diagram_element_id,
            "binding": mat.binding or mat.proposed_binding,
            "warnings": mat.warnings,
            "error": mat.error,
        }

    if not source_entity or not target_entity:
        return {"error": "source_entity and target_entity are required when from_diagram_element is not provided"}

    out = _add_connection_impl(
        source_entity=source_entity,
        connection_type=connection_type,
        target_entity=target_entity,
        description=description,
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
        specialization=specialization,
        specializations=specializations,
        metadata=metadata,
        version=version,
        status=status,
        dry_run=dry_run,
        repo_root=repo_root,
        provisional_ids=frozenset(),
        clear_repo_caches=clear_repo_caches,
    )
    if not dry_run and mutation_context.changed_paths:
        mutation_context.finalize()
    return out


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_add_connection,
        name="artifact_add_connection",
        title="Artifact Write: Add Connection",
        description=(
            "Add a connection to an entity's .outgoing.md file. Defaults use repos from "
            "arch-init workspace config (repo_root optional). "
            "Connecting from/to a global entity automatically creates a per-engagement "
            "proxy (global-entity-reference) if one does not already exist — handles "
            "outgoing, incoming, and symmetric connections transparently. "
            "Optional src_multiplicity / tgt_multiplicity annotate the source or target end "
            "of the connection (e.g. '1', '0..1', '1..*', '*'). "
            "Junction endpoints: multiplicities prohibited; all connections at a junction "
            "must share the same type (first connection locks it). "
            "dry_run=true returns would-be content without writing. "
            "source_entity/target_entity: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
