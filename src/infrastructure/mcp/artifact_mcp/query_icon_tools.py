"""MCP read tool: which icons of the library may be shown on an element, and what each is."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.application.icons.icon_rows import icon_fields, usage_fields
from src.application.icons.icon_usage import library_usage
from src.application.icons.library_query import offered_icons
from src.application.modeling.proposal_standing import standing_reader, standing_subject
from src.domain.artifact_id import stable_id
from src.domain.baseline_standing import BASELINE_STANDING
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.context import RepoScope, repo_cached, resolve_repo_roots, roots_key
from src.infrastructure.mcp.tool_annotations import READ_ONLY


def artifact_query_icons(
    *,
    applicable_to: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    include_retired: bool = False,
    repo_root: str | None = None,
    repo_scope: RepoScope = "both",
) -> list[dict[str, object]]:
    roots = resolve_repo_roots(repo_scope=repo_scope, repo_root=repo_root, repo_preset=None, enterprise_root=None)
    repo = repo_cached(roots_key(roots))
    offered = offered_icons(
        repo.list_icons(), applicable_to=applicable_to, tag=tag, text=q,
        include_retired=include_retired, entity_of=repo.get_entity,
    )
    standing_of = standing_reader(repo)
    usage = library_usage(repo.list_diagrams(), process_runtime_catalogs().specializations)
    shown_for = usage.shown_for(applicable_to) if applicable_to else frozenset()
    return [
        {
            **icon_fields(icon),
            **usage_fields(usage.users_of(icon.artifact_id)),
            "shown_for_element": stable_id(icon.artifact_id) in shown_for,
            "scope": repo.scope_for_path(icon.path),
            BASELINE_STANDING: standing_of(standing_subject(icon)).to_mapping(),
        }
        for icon in offered
    ]


def register_query_icon_tools(mcp: MCPServer) -> None:
    mcp.tool(
        name="artifact_query_icons",
        title="Artifact Query: Icons",
        description=(
            "List the icons of the library a diagram may show. applicable_to is what you are choosing "
            "for — an entity id, or an entity type or specialization name — and keeps only icons that "
            "may be shown there; tag keeps icons carrying that tag; q matches name and attribution. "
            "Retired icons are left out unless include_retired. Each row gives what to choose by "
            "(name, attribution, applies_to, default_style, tags, size) and never the picture, where it "
            "is used (used_on: the diagrams naming it; default_for: the specializations defaulting to "
            "it), and shown_for_element: whether a diagram already shows it for the entity applicable_to "
            "names, so a logo chosen for an element once can be chosen again. Assign "
            "one with artifact_create_diagram / artifact_edit_diagram through "
            "diagram_entities.display_icons (per instance) or type_icons (per type or specialization "
            "name); add one with artifact_create_icon. repo_scope defaults to both tiers; where both "
            "hold an icon, the engagement's copy stands for it."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )(artifact_query_icons)
