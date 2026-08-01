"""MCP write tools: matrix and diagram creation."""

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE
from src.infrastructure.mcp.artifact_mcp.write._common import (
    DiagramConnectionInferenceMode,
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)


def artifact_create_matrix(
    *,
    name: str,
    matrix_markdown: str,
    artifact_id: str | None = None,
    keywords: list[str] | None = None,
    diagram_entities: dict[str, object] | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    infer_entity_ids: bool = True,
    auto_link_entity_ids: bool = True,
    tlp: str | None = None,
    group: str | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    key = roots_key(roots)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.create_matrix(
        repo_root=roots[0],
        registry=registry_cached(key),
        verifier=verifier_for(key, include_registry=True),
        clear_repo_caches=clear_repo_caches,
        name=name,
        matrix_markdown=matrix_markdown,
        artifact_id=artifact_id,
        keywords=keywords,
        version=version,
        status=status,
        last_updated=None,
        infer_entity_ids=infer_entity_ids,
        auto_link_entity_ids=auto_link_entity_ids,
        tlp=tlp,
        group=group,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_create_diagram(
    *,
    diagram_type: str,
    name: str,
    puml: str = "",
    entity_ids: list[str] | None = None,
    direction: Literal["top_to_bottom", "left_to_right"] = "top_to_bottom",
    artifact_id: str | None = None,
    keywords: list[str] | None = None,
    diagram_entities: dict[str, object] | None = None,
    diagram_connections: list[dict[str, object]] | None = None,
    view_derivations: list[dict[str, object]] | None = None,
    bindings: list[dict[str, object]] | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    tlp: str | None = None,
    viewpoint: dict[str, object] | None = None,
    group: str | None = None,
    connection_inference: DiagramConnectionInferenceMode = "none",
    auto_include_stereotypes: bool = True,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    entity_ids_used: list[str] | None = None
    connection_ids_used: list[str] | None = None
    if entity_ids and not puml:
        from src.infrastructure.mcp.artifact_mcp.context import expand_artifact_id  # noqa: PLC0415
        from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body  # noqa: PLC0415
        from src.infrastructure.rest.routers.diagrams._selection import resolve_diagram_selection  # noqa: PLC0415

        roots = resolve_repo_roots(
            repo_scope="engagement",
            repo_root=repo_root,
            repo_preset=None,
            enterprise_root=None,
        )
        key = roots_key(roots)
        repo = repo_cached(key)
        expanded_entity_ids = [expand_artifact_id(repo, eid) for eid in entity_ids]
        entity_id_set = set(expanded_entity_ids)
        auto_connection_ids = [
            str(conn["artifact_id"])
            for conn in repo.candidate_connections_for_entities(expanded_entity_ids)
            if str(conn["source"]) in entity_id_set and str(conn["target"]) in entity_id_set
        ]
        entities, connections, entity_ids_used, connection_ids_used = resolve_diagram_selection(
            repo,
            expanded_entity_ids,
            auto_connection_ids,
        )
        puml = generate_archimate_puml_body(
            name,
            entities,
            connections,
            diagram_type=diagram_type,
            repo_root=roots[0],
            diagram_entities=diagram_entities,
            diagram_connections=diagram_connections,
        )

    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    key = roots_key(roots)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    from src.domain.repository.groups import UNCATEGORIZED  # noqa: PLC0415

    result = artifact_write_ops.create_diagram(
        repo_root=roots[0],
        verifier=verifier_for(key, include_registry=True),
        clear_repo_caches=clear_repo_caches,
        diagram_type=diagram_type,
        name=name,
        puml=puml,
        artifact_id=artifact_id,
        keywords=keywords,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
        view_derivations=view_derivations,
        bindings=bindings,
        entity_ids_used=entity_ids_used,
        connection_ids_used=connection_ids_used,
        version=version,
        status=status,
        last_updated=None,
        tlp=tlp,
        viewpoint=viewpoint,
        connection_inference=connection_inference,
        auto_include_stereotypes=auto_include_stereotypes,
        dry_run=dry_run,
        group=group or UNCATEGORIZED,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_create_matrix,
        name="artifact_create_matrix",
        title="Artifact Write: Create Connection Matrix",
        description=(
            "Create a markdown connection-matrix diagram. Defaults to engagement repo from "
            "arch-init config. dry_run=true returns would-be content without writing. "
            "Passing an existing artifact_id upserts it in place (resolved via the registry, "
            "honouring any diagram-collection group it already lives in) instead of creating "
            "a duplicate at the flat path. group (str|None) re-homes it to a diagram-collection "
            "slug; for a metadata-only group/name/version/status move without resupplying the "
            "table, use artifact_edit_diagram instead. "
            "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_create_diagram,
        name="artifact_create_diagram",
        title="Artifact Write: Create Diagram",
        description=(
            "Create a diagram. Always call artifact_authoring_guidance(diagram_type=...) first — "
            "it returns when_to_use guidance, the diagram_entities schema, and per-type authoring notes.\n\n"
            "ArchiMate views — two authoring modes:\n"
            "  1. entity_ids=[...]: pass a list of artifact_ids; PUML is auto-generated via render_body() "
            "using existing model connections. Fastest path for new diagrams — no manual PUML needed.\n"
            "  2. puml=...: supply PUML manually using entity display_alias values "
            "(artifact_query_read_artifact mode='full') for custom layouts.\n"
            "For ArchiMate views, diagram_connections is optional per-diagram connection annotation metadata keyed by "
            "model connection artifact_id. It does not create diagram-owned connections. Supported opt-in keys are "
            "artifact_id (or connection_id), include_description, include_multiplicity, and label.\n"
            "For additional occurrences of an already included model entity, pass "
            "diagram_entities={'occurrence': [{'id': '<occurrence-id>', 'backing_entity_id': '<model-entity-id>'}]}. "
            "The occurrence id distinguishes the diagram element; backing_entity_id preserves the single model "
            "identity. visual_role is optional metadata, not required for identity.\n"
            "direction='left_to_right' | 'top_to_bottom' (default). "
            "auto_include_stereotypes=true injects !include lines. "
            "connection_inference: 'none' | 'auto' (warn) | 'strict' (error) on unknown stereotypes.\n\n"
            "Diagram-owned views (activity, C4): omit puml and entity_ids; pass diagram_entities per the schema. "
            "PUML is generated automatically; diagram_entities is persisted for round-trip editing.\n\n"
            "Bindings: pass bindings=[...] for explicit top-level bindings, or put a nested binding: key on "
            "diagram_entities items (single-target shorthand: entity_id, connection_id, or diagram_local). "
            "Legacy entity_id on items and _scope_entity_id in diagram_entities are accepted as input shorthand "
            "and normalized to top-level bindings on write.\n\n"
            "tlp: classification (TLP:WHITE|GREEN|AMBER|RED) for assurance diagram types. TLP:WHITE/GREEN are "
            "publishable (rendered + source persisted to the shared catalog); TLP:AMBER/RED (or unset) are "
            "confidential — source is redirected to a gitignored confidential/ root and rendering to disk is "
            "withheld. Ignored for non-assurance diagram types.\n\n"
            "viewpoint: apply a ViewpointDefinition to narrow this diagram's authoring scope — "
            "{slug, version, enforcement_override?, derivation_params?}. Call "
            "artifact_query_viewpoint(action='list') to discover slugs/versions.\n\n"
            "dry_run=true validates without writing."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
