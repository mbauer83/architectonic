"""MCP read tool for listing and executing viewpoint definitions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.viewpoints.evaluate_viewpoint import (
    UnknownViewpointSlugError,
    ViewpointExecutionRequest,
    ViewpointExecutionTimeoutError,
    evaluate_viewpoint,
)
from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.application.viewpoints.pins import load_pinned_slugs
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
    viewpoints_execution_default_entity_limit_mcp,
    viewpoints_execution_max_entities,
    viewpoints_execution_timeout_seconds,
    viewpoints_legibility_budget,
)
from src.domain.relationships.relationship_reachability import DerivationLimitError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.domain.viewpoints.viewpoint_lineage import fork_status
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoint_scope_query import definition_with_scope_query
from src.domain.viewpoints.viewpoint_summary import render_query_summary
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.assurance.signal_attribute_capability import (
    composed_signal_attribute_capability,
)
from src.infrastructure.mcp.artifact_mcp.context import (
    RepoScope,
    repo_cached,
    resolve_repo_root,
    resolve_repo_roots,
    roots_key,
    runtime_catalogs,
)
from src.infrastructure.mcp.artifact_mcp.tool_annotations import READ_ONLY
from src.infrastructure.viewpoint_declarations import load_effective_viewpoint_catalog
from src.infrastructure.write.artifact_write.viewpoint_type_guidance import summarize_scope


def _list_entry(
    definition: ViewpointDefinition, *, pinned_slugs: frozenset[str], merged: ViewpointCatalog
) -> dict[str, object]:
    # The listing must describe the ACTIVE selection: a scope-mode definition's
    # (possibly divergent) inactive query never appears as its summary.
    active_query = definition_with_scope_query(definition)[0].query
    return {
        "slug": definition.slug,
        "version": definition.version,
        "name": definition.name,
        "description": definition.description,
        "purpose": list(definition.purpose),
        "content": list(definition.content),
        "stakeholders": list(definition.stakeholders),
        "concerns": list(definition.concerns),
        "scope_summary": summarize_scope(definition.scope),
        "query_summary": (
            render_query_summary(active_query, default_derivation_max_hops=viewpoints_derivation_max_hops())
            if active_query is not None
            else None
        ),
        "parameters": [
            {"name": parameter.name, "type": parameter.value_type, "required": parameter.required}
            for parameter in (() if definition.query is None else definition.query.parameters)
        ],
        "pinned": definition.slug in pinned_slugs,
        "forked_from": (
            {
                "slug": definition.forked_from.slug,
                "version": definition.forked_from.version,
            }
            if definition.forked_from is not None
            else None
        ),
        # Staleness by content-digest comparison against the CURRENT origin, never by
        # version comparison — versions are hand-edited integers.
        "fork_status": fork_status(
            definition.forked_from,
            merged.get(definition.forked_from.slug) if definition.forked_from is not None else None,
        ),
    }


def register_query_viewpoint_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="artifact_query_viewpoint",
        title="Artifact Query: Viewpoints",
        description=(
            "action='list': browse the effective merged viewpoint catalog — slug/version/name/"
            "purpose/content/stakeholders/concerns, a scope summary, a plain-language "
            "query_summary so you see what a viewpoint means, not just that it exists, and "
            "whether it is pinned (engagement-repo-local quick access). "
            "action='execute': run a definition's query (slug=...) or an ad-hoc query "
            "(query=..., in the viewpoint-definition schema — see artifact_help's 'viewpoints' "
            "topic for the grammar); returns sorted entity/connection ids with fixed summaries, four counts, "
            "truncation, matrix_axes (criteria-axes matrix only), warnings, and the echoed "
            "query_summary. No presentation/styling/column parameters exist here. "
            "limit (execute only) is entity-denominated, defaults small to protect context, "
            "clamped to the hard cap."
            "\n\nRepo selection: repo_scope defaults to both (engagement + enterprise)."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_query_viewpoint(
        action: Literal["list", "execute"],
        slug: str | None = None,
        query: dict[str, object] | None = None,
        limit: int | None = None,
        parameters: dict[str, object] | None = None,
        repo_root: str | None = None,
        repo_scope: RepoScope = "both",
    ) -> dict[str, object]:
        roots = resolve_repo_roots(repo_scope=repo_scope, repo_root=repo_root, repo_preset=None, enterprise_root=None)
        merged_catalog = load_effective_viewpoint_catalog(roots)

        if action == "list":
            engagement_root = resolve_repo_root(repo_root=repo_root, repo_preset=None)
            known_slugs = frozenset(d.slug for d in merged_catalog.entries)
            pinned_slugs = frozenset(load_pinned_slugs(engagement_root, known_slugs=known_slugs).slugs)
            entries = [
                _list_entry(d, pinned_slugs=pinned_slugs, merged=merged_catalog)
                for d in sorted(merged_catalog.entries, key=lambda d: d.slug)
            ]
            return {"viewpoints": entries}

        if (slug is None) == (query is None):
            raise ValueError("action='execute' requires exactly one of 'slug' or 'query'")
        parsed_query = query_from_mapping(query, label="query") if query is not None else None
        request = ViewpointExecutionRequest(slug=slug, query=parsed_query, limit=limit, parameters=parameters)

        catalogs = runtime_catalogs()
        repo = repo_cached(roots_key(roots))
        registries = build_registry_snapshot(
            catalogs,
            repo.repo_roots,
            derivation_max_hops=viewpoints_derivation_max_hops(),
            derivation_max_relationships=viewpoints_derivation_max_relationships(),
            derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
        )
        try:
            result = evaluate_viewpoint(
                request,
                catalog=merged_catalog,
                read_access=repo,
                registries=registries,
                index_generation=repo.read_model_version().generation,
                max_entities=viewpoints_execution_max_entities(),
                default_limit=viewpoints_execution_default_entity_limit_mcp(),
                default_legibility_budget=viewpoints_legibility_budget(),
                timeout_seconds=viewpoints_execution_timeout_seconds(),
                signal_capability=composed_signal_attribute_capability(),
            )
        except UnknownViewpointSlugError as exc:
            raise ValueError(str(exc)) from exc
        except ViewpointParameterError as exc:
            return {"error": {"code": exc.code, "path": f"parameters/{exc.parameter}", "message": str(exc)}}
        except BindingCardinalityError as exc:
            return {"error": {"code": exc.code, "path": "query", "message": str(exc)}}
        except DerivationLimitError as exc:
            return {"error": {"code": "derivation-limit", "path": "query", "message": str(exc)}}
        except ViewpointExecutionTimeoutError as exc:
            return {"error": {"code": "execution-timeout", "path": "query", "message": str(exc)}}
        return asdict(result)
