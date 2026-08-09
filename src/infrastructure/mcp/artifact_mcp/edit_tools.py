"""MCP tool definitions for editing entities, connections, and diagrams."""

from pathlib import Path
from typing import Any, Final, Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.mcp.artifact_mcp import edit_tool_descriptions as descriptions
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    expand_artifact_id,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.artifact_mcp.write._common import _out
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE
from src.infrastructure.write import artifact_write_ops

PUML_AUTO_SYNC: Final[Literal["auto-sync"]] = "auto-sync"


def _result_dict(dry_run: bool, result: artifact_write_ops.WriteResult) -> dict[str, object]:
    return _out(result, dry_run=dry_run)


def _resolve(repo_root: str | None, *, need_registry: bool) -> tuple[Path, ArtifactRegistry | None, ArtifactVerifier]:
    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    key = roots_key(roots)
    registry = registry_cached(key) if need_registry else None
    verifier = verifier_for(key, include_registry=need_registry)
    return roots[0], registry, verifier


def _require_registry(registry: ArtifactRegistry | None) -> ArtifactRegistry:
    if registry is None:
        raise RuntimeError("Registry is required for this operation")
    return registry


def _finalize_authoritative_write(
    dry_run: bool,
    result: artifact_write_ops.WriteResult,
    mutation_context,
) -> dict[str, object]:
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _result_dict(dry_run, result)


def artifact_edit_entity(
    *,
    artifact_id: str,
    name: str | None = None,
    summary: str | None = None,
    properties: dict[str, object] | None = None,
    attribute_types: dict[str, str] | None = None,
    notes: str | None = None,
    keywords: list[str] | None = None,
    specializations: list[str] | None = None,
    version: str | None = None,
    status: str | None = None,
    group: str | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    root, registry, verifier = _resolve(repo_root, need_registry=True)
    registry = _require_registry(registry)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)
    artifact_id = expand_artifact_id(registry, artifact_id)

    kwargs: dict[str, Any] = {
        k: v for k, v in (
            ("name", name), ("summary", summary), ("properties", properties),
            ("attribute_types", attribute_types),
            ("notes", notes), ("keywords", keywords),
            ("specializations", specializations),
            ("version", version), ("status", status), ("group", group),
        ) if v is not None
    }

    result = artifact_write_ops.edit_entity(
        repo_root=root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
        **kwargs,
    )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


_EDIT_CONN_UNSET = object()


def artifact_edit_connection(
    *,
    source_entity: str,
    target_entity: str,
    connection_type: str,
    operation: str = "update",
    description: str | None = None,
    src_multiplicity: str | None = None,
    tgt_multiplicity: str | None = None,
    specializations: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    """Edit or remove a connection.

    For operation='update': description, src_multiplicity, tgt_multiplicity, specializations,
    metadata are applied. Pass "" for a multiplicity or [] for specializations to remove them; omit
    (None) to preserve it. metadata REPLACES the schema-declared per-connection attributes
    wholesale; pass {} to clear them.
    """
    root, registry, verifier = _resolve(repo_root, need_registry=True)
    registry = _require_registry(registry)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)
    source_entity = expand_artifact_id(registry, source_entity)
    target_entity = expand_artifact_id(registry, target_entity)

    if operation == "remove":
        result = artifact_write_ops.remove_connection(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            source_entity=source_entity,
            target_entity=target_entity,
            connection_type=connection_type,
            dry_run=dry_run,
        )
    else:
        from src.infrastructure.write.artifact_write.connection_edit import _UNSET

        result = artifact_write_ops.edit_connection(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            source_entity=source_entity,
            target_entity=target_entity,
            connection_type=connection_type,
            description=description if description is not None else _UNSET,
            src_multiplicity=src_multiplicity if src_multiplicity is not None else _UNSET,
            tgt_multiplicity=tgt_multiplicity if tgt_multiplicity is not None else _UNSET,
            specializations=specializations if specializations is not None else _UNSET,
            metadata=metadata if metadata is not None else _UNSET,
            dry_run=dry_run,
        )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


def artifact_edit_diagram(
    *,
    artifact_id: str,
    mode: str | None = None,
    puml: str | Literal["auto-sync"] | None = None,
    name: str | None = None,
    keywords: list[str] | None = None,
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    view_derivations: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    version: str | None = None,
    status: str | None = None,
    tlp: str | None = None,
    viewpoint: dict[str, object] | None = None,
    edge_labels: dict[str, str | None] | None = None,
    derivation_id: str | None = None,
    diff: dict[str, object] | None = None,
    base_revision: str | None = None,
    entity_ids: list[str] | None = None,
    connection_ids: list[str] | None = None,
    binding_id: str | None = None,
    authored_groupings: list[dict[str, object]] | None = None,
    group: str | None = None,
    manual_layout: bool | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    key = roots_key(roots)
    root = roots[0]

    if mode is not None:
        from src.infrastructure.mcp.artifact_mcp._diagram_binding_modes import dispatch_binding_mode  # noqa: PLC0415
        return dispatch_binding_mode(
            mode=mode, artifact_id=artifact_id, root=root, key=key,
            derivation_id=derivation_id, diff=diff, base_revision=base_revision,
            entity_ids=entity_ids, connection_ids_param=connection_ids,
            binding_id=binding_id, dry_run=dry_run,
        )

    verifier = verifier_for(key, include_registry=True)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    committed_repo = committed_repository(repo_cached(key))

    if puml == PUML_AUTO_SYNC:
        store = repo_cached(key)
        result = artifact_write_ops.refresh_diagram(
            repo_root=root,
            store=store,
            verifier=verifier,
            clear_repo_caches=clear_repo_caches,
            artifact_id=artifact_id,
            dry_run=dry_run,
        )
        out = _finalize_authoritative_write(dry_run, result, mutation_context)
        out["removed_entity_ids"] = result.removed_entity_ids
        out["removed_connection_ids"] = result.removed_connection_ids
        out["deleted_diagram"] = result.deleted_diagram
        return out

    states_membership = entity_ids is not None or connection_ids is not None or authored_groupings is not None
    if puml is None and states_membership:
        # Membership or grouping stated without a body: the picture is regenerated from it, so a
        # removal is a removal and a box appears. Composed into this same edit rather than written
        # separately, so anything else the call carries still applies. A diagram whose body is not
        # the generator's to rewrite is refused.
        puml, entity_ids, connection_ids, authored_groupings = artifact_write_ops.rendered_membership(
            repo_root=root, store=repo_cached(key), verifier=verifier, artifact_id=artifact_id,
            entity_ids=entity_ids, connection_ids=connection_ids, authored_groupings=authored_groupings)

    kwargs: dict[str, Any] = {
        k: v for k, v in (
            ("puml", puml), ("name", name), ("keywords", keywords),
            ("diagram_entities", diagram_entities), ("diagram_connections", diagram_connections),
            ("view_derivations", view_derivations), ("bindings", bindings),
            ("version", version), ("status", status), ("tlp", tlp), ("group", group),
            ("viewpoint", viewpoint),
            ("entity_ids_used", entity_ids), ("connection_ids_used", connection_ids),
            ("authored_groupings", authored_groupings),
            ("manual_layout", manual_layout),
        ) if v is not None
    }
    if edge_labels is not None:
        kwargs["edge_labels"] = edge_labels

    result = artifact_write_ops.edit_diagram(
        repo_root=root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
        committed_repo=committed_repo,
        **kwargs,
    )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


def artifact_edit_connection_associations(
    *,
    source_entity: str,
    connection_type: str,
    target_entity: str,
    add_entities: list[str] | None = None,
    remove_entities: list[str] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    """Add or remove second-order association entity IDs from a connection."""
    root, registry, verifier = _resolve(repo_root, need_registry=True)
    registry = _require_registry(registry)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)
    source_entity = expand_artifact_id(registry, source_entity)
    target_entity = expand_artifact_id(registry, target_entity)
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection_associations

    result = edit_connection_associations(
        repo_root=root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        source_entity=source_entity,
        connection_type=connection_type,
        target_entity=target_entity,
        add_entities=add_entities,
        remove_entities=remove_entities,
        dry_run=dry_run,
    )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


def register_edit_tools(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.delete_tools import register_delete_tools  # noqa: PLC0415
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_edit_entity,
        name="artifact_edit_entity",
        title="Artifact Write: Edit Entity",
        description=descriptions.EDIT_ENTITY_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_edit_connection,
        name="artifact_edit_connection",
        title="Artifact Write: Edit/Remove Connection",
        description=descriptions.EDIT_CONNECTION_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_edit_diagram,
        name="artifact_edit_diagram",
        title="Artifact Write: Edit Diagram",
        description=descriptions.EDIT_DIAGRAM_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_edit_connection_associations,
        name="artifact_edit_connection_associations",
        title="Artifact Write: Edit Connection Associations",
        description=descriptions.EDIT_CONNECTION_ASSOCIATIONS_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_delete_tools(mcp)
