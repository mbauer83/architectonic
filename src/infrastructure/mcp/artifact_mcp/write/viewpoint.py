"""MCP write tool: artifact_viewpoint — create/edit/delete viewpoint definitions. A
definition is model content, not hand-edited configuration: this runs the same
``persist_edit``-mode validation and catalog-file persistence a GUI builder's save flow
would use — one write path, two front ends. Engagement-repo scope only; read the effective
merged catalog via ``artifact_query_viewpoint``.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.viewpoints.persist_definition import (
    delete_viewpoint_definition,
    persist_viewpoint_definition,
)
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.infrastructure.mcp.artifact_mcp.context import repo_cached, resolve_repo_roots, roots_key, runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE
from src.infrastructure.viewpoint_declarations import (
    load_effective_viewpoint_catalog,
    load_viewpoint_catalog_file,
    write_viewpoint_catalog_file,
)


def artifact_viewpoint(
    *,
    action: Literal["create", "edit", "delete"],
    slug: str | None = None,
    definition: dict[str, object] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
    fork_of: str | None = None,
) -> dict[str, object]:
    """create/edit: definition is the full viewpoint-definition mapping (slug,
    version, name, scope, query, presentation, ...) — see artifact_help's 'viewpoints' topic
    for the grammar. delete: slug only. Engagement-repo scope: enterprise/module-shipped
    definitions are read-only here. dry_run=True (default) validates and reports without
    writing; dry_run=False applies. Semantic edits (scope/query/presentation/
    representation_types) require a version bump; descriptive-only edits don't. Delete is
    blocked while any diagram/matrix references the slug — the referencers list names them.
    """
    engagement_roots = resolve_repo_roots(
        repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None
    )
    engagement_root = engagement_roots[0]
    both_roots = resolve_repo_roots(repo_scope="both", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    merged_catalog = load_effective_viewpoint_catalog(both_roots)
    local_catalog = load_viewpoint_catalog_file(engagement_root)
    registries = build_registry_snapshot(
        runtime_catalogs(),
        both_roots,
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )

    if action == "delete":
        if slug is None:
            return {"error": "action='delete' requires 'slug'", "action": action}
        repo = repo_cached(roots_key(both_roots))
        result = delete_viewpoint_definition(
            slug, local_catalog=local_catalog, merged_catalog=merged_catalog, read_access=repo
        )
    else:
        if definition is None:
            return {"error": f"action={action!r} requires 'definition'", "action": action}
        try:
            parsed = viewpoint_definition_from_mapping(definition)
        except ValueError as exc:
            return {"error": str(exc), "action": action}
        # The model generation is only recorded into fork lineage — plain creates/edits
        # never touch the repo index at all.
        index_generation = (
            repo_cached(roots_key(both_roots)).read_model_version().generation if fork_of is not None else None
        )
        result = persist_viewpoint_definition(
            action,
            parsed,
            local_catalog=local_catalog,
            merged_catalog=merged_catalog,
            registries=registries,
            fork_of=fork_of,
            index_generation=index_generation,
        )

    if result.ok and not dry_run and result.catalog_to_write is not None:
        write_viewpoint_catalog_file(engagement_root, result.catalog_to_write)
        runtime_catalogs.cache_clear()
    return result.as_answer(dry_run=dry_run)


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_viewpoint,
        name="artifact_viewpoint",
        title="Artifact Write: Viewpoint Definitions",
        description=(
            "Create/edit/delete a ViewpointDefinition in the engagement repo's own catalog — "
            "the same validate/persist path a GUI builder's save flow uses. "
            "action: create | edit | delete. "
            "definition (create/edit): the full viewpoint-definition mapping — see "
            "artifact_help's 'viewpoints' topic for the grammar. slug (delete only). "
            "Engagement-repo scope: enterprise/module-shipped definitions are read-only here. "
            "Semantic edits (scope/query/presentation/representation_types) require a version "
            "bump; descriptive-only edits don't. Delete is blocked while any diagram/matrix "
            "references the slug (referencers lists them — no force flag). "
            "fork_of (create only): origin slug when the new definition is a fork — lineage "
            "(origin slug/version/content digest + model generation) is stamped server-side; "
            "GUI- and MCP-created forks carry identical lineage. "
            "dry_run: True (default) validates/reports without writing, False applies. "
            "Read the effective merged catalog via artifact_query_viewpoint (arch-repo-read)."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
