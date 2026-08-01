"""MCP write tools: entity creation and catalog help."""

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE, READ_ONLY
from src.infrastructure.mcp.artifact_mcp.write._common import (
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)


def artifact_help() -> dict[str, object]:
    return artifact_write_ops.write_help()


def artifact_authoring_guidance(
    filter: list[str] | None = None,  # noqa: A002
    diagram_type: str | None = None,
    target: str | None = None,
) -> dict[str, object]:
    from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_root  # noqa: PLC0415

    return artifact_write_ops.get_type_guidance(
        filter=filter,
        diagram_type=diagram_type,
        target=target,
        catalogs=process_runtime_catalogs(),
        # REST/MCP parity: the connection metadata schemata are per-repo files, so both
        # transports must resolve a root or neither can carry them.
        repo_root=resolve_repo_root(repo_root=None, repo_preset=None),
    )


def artifact_create_entity(
    *,
    artifact_type: str,
    name: str,
    summary: str | None = None,
    properties: dict[str, object] | None = None,
    attribute_types: dict[str, str] | None = None,
    notes: str | None = None,
    keywords: list[str] | None = None,
    specialization: str | None = None,
    specializations: list[str] | None = None,
    artifact_id: str | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    group: str | None = None,
    from_diagram_element: dict[str, object] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    root = roots[0]

    if from_diagram_element:
        from src.infrastructure.write.artifact_write.materialization import (  # noqa: PLC0415
            DiagramElementRef,
            materialize_entity,
        )
        ref = DiagramElementRef(
            diagram_id=str(from_diagram_element.get("diagram_id", "")),
            diagram_element_id=str(from_diagram_element.get("diagram_element_id", "")),
            diagram_element_kind=str(from_diagram_element.get("diagram_element_kind", "entity")),
            correspondence_kind_after=str(from_diagram_element.get("correspondence_kind_after", "represents")),
        )
        mat = materialize_entity(
            repo_root=root,
            verifier=verifier_for(roots_key(roots), include_registry=False),
            clear_repo_caches=clear_repo_caches,
            ref=ref, artifact_type=artifact_type, name=name,
            summary=summary, properties=properties, attribute_types=attribute_types, notes=notes, keywords=keywords,
            version=version, status=status, dry_run=dry_run,
        )
        if mat.wrote and not dry_run:
            mutation_context.finalize()
        return {
            "dry_run": dry_run,
            "wrote": mat.wrote,
            "entity_id": mat.entity_id,
            "proposed_entity_id": mat.proposed_entity_id,
            "diagram_id": mat.diagram_id,
            "diagram_element_id": mat.diagram_element_id,
            "binding": mat.binding or mat.proposed_binding,
            "proposed_content": mat.proposed_content,
            "verification": mat.verification,
            "warnings": mat.warnings,
            "error": mat.error,
        }

    from src.domain.repository.groups import UNCATEGORIZED  # noqa: PLC0415

    result = artifact_write_ops.create_entity(
        repo_root=root,
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        artifact_type=artifact_type,
        name=name,
        summary=summary,
        properties=properties,
        attribute_types=attribute_types,
        notes=notes,
        keywords=keywords,
        specialization=specialization,
        specializations=specializations,
        artifact_id=artifact_id,
        version=version,
        status=status,
        last_updated=None,
        dry_run=dry_run,
        group=group or UNCATEGORIZED,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    mcp.tool(
        name="artifact_help",
        title="Artifact: Type Catalog",
        description=(
            "Return the full catalog of artifact types, entity types (by domain), connection types "
            "(by language), and diagram types (with accepted domains). "
            "Call this first to discover valid type names — guessing them causes validation errors. "
            "For detailed authoring guidance call artifact_authoring_guidance."
        ),
        annotations=READ_ONLY,
        structured_output=False,
    )(artifact_help)

    mcp.tool(
        name="artifact_authoring_guidance",
        title="Artifact: Authoring Guidance",
        description=(
            "Return authoring guidance before creating entities or diagrams. "
            "Three independent params (usable separately or together):\n"
            "• diagram_type (str): diagram type block — when_to_use, when_not_to_use, "
            "accepted_domains, own entity types, diagram_entities schema, and optional puml_notes.\n"
            "• filter (list[str]): entity type guidance — create_when, never_create_when, "
            "permitted_connections, specializations (available specialization slugs for that "
            "type, with their own guidance), and an optional context array: layered guidance "
            "context composed along the type's ancestry (e.g. its domain), broadest first — "
            "present only when such context has been imported. Pass type names (e.g. "
            "['requirement', 'goal']) or domain names (e.g. ['motivation', 'strategy']) — not "
            "mixed. The response also includes connection_types: per relationship type, its own "
            "create_when/never_create_when (which relationship to reach for, and what it is "
            "confused with) plus any declared specializations.\n"
            "• target (str): pair-legality — requires filter with exactly one concrete type name; "
            "returns pair_guidance {outgoing, incoming, symmetric} for the (source, target) pair.\n"
            "Omit all to return all entity type guidance (large; prefer filtering).\n\n"
            "Datatype diagrams — attribute type contract: each attribute's 'type' field is either "
            "{kind: 'primitive', name: '<name>'} for built-in scalar types, or "
            "{kind: 'classifier', id: '<type_id>'} for a named classifier type. "
            "Call artifact_query_datatype_types to discover available type_ids.\n\n"
            "To discover viewpoints to apply (via artifact_create_diagram/artifact_edit_diagram's "
            "'viewpoint' parameter), use artifact_query_viewpoint(action='list') — this tool covers "
            "entity/connection/diagram-type authoring only."
        ),
        annotations=READ_ONLY,
        structured_output=False,
    )(artifact_authoring_guidance)

    register_mutation_tool(
        mcp,
        artifact_create_entity,
        name="artifact_create_entity",
        title="Artifact Write: Create Entity",
        description=(
            "Create a model entity file. Defaults to the engagement repo from arch-init workspace "
            "config (repo_root optional). dry_run=true validates without writing. "
            "group: model-project slug to place the entity in (default: 'uncategorized'). "
            "from_diagram_element: {diagram_id, diagram_element_id, diagram_element_kind='entity', "
            "correspondence_kind_after='represents'} — when provided, atomically creates the entity "
            "and attaches a binding to the diagram element (materialization)."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
