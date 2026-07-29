"""Manifest-required registration for MCP mutation tools.

Every mutating MCP tool registers exclusively through ``register_mutation_tool``,
which requires a manifest row (declared intents + a per-call request builder) and
installs the AuthorizedMutationExecutor around the tool body — an unmanifested
mutator cannot register, so policy coverage is structural, not observational.
Tools on the write server that perform no repository mutation are classified
explicitly in ``NON_MUTATING_WRITE_TOOLS``. Dry-run/validation variants of the
mutators route through the executor like live calls (fail-closed serialization,
identical to their previous queue behavior).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationIntent,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)
from src.infrastructure.mcp.artifact_mcp.context import resolve_enterprise_repo_root, resolve_repo_root
from src.infrastructure.write.mutation_executor_registry import (
    _reset_executor_for_test,  # noqa: F401  (re-export: test harness reset)
    install_mutation_executor,  # noqa: F401  (re-export: composition-root install)
    mutation_executor,
)

ToolArguments = Mapping[str, object]


@dataclass(frozen=True)
class MutationToolManifestRow:
    """Authorization identity of one mutating MCP tool."""

    intents: tuple[MutationIntent, ...]
    build_request: Callable[[ToolArguments], MutationRequest]


def _repo_root_argument(arguments: ToolArguments) -> str | None:
    value = arguments.get("repo_root")
    return value if isinstance(value, str) else None


def _engagement_authoring(arguments: ToolArguments) -> MutationRequest:
    root = resolve_repo_root(repo_root=_repo_root_argument(arguments), repo_preset=None)
    return MutationRequest("engagement_authoring", RepositoryWrite(root))


def _promotion(arguments: ToolArguments) -> MutationRequest:
    enterprise = arguments.get("enterprise_root")
    return MutationRequest(
        "promotion",
        PromotionWrite(
            source_root=resolve_repo_root(repo_root=_repo_root_argument(arguments), repo_preset=None),
            destination_root=resolve_enterprise_repo_root(
                enterprise_root=enterprise if isinstance(enterprise, str) else None
            ),
        ),
    )


def _configured_engagement_root() -> Path:
    from src.infrastructure.gui.routers import state as gui_state  # noqa: PLC0415

    root = gui_state.maybe_engagement_root()
    return root if root is not None else resolve_repo_root(repo_root=None, repo_preset=None)


def _configured_enterprise_root() -> Path:
    from src.infrastructure.gui.routers import state as gui_state  # noqa: PLC0415

    root = gui_state.maybe_enterprise_root()
    return root if root is not None else resolve_enterprise_repo_root(enterprise_root=None)


def _save_changes(arguments: ToolArguments) -> MutationRequest:
    if arguments.get("target") == "enterprise":
        return MutationRequest("enterprise_save", RepositoryWrite(_configured_enterprise_root()))
    return MutationRequest("engagement_authoring", RepositoryWrite(_configured_engagement_root()))


def _enterprise_submit(arguments: ToolArguments) -> MutationRequest:
    return MutationRequest("enterprise_submit", RepositoryWrite(_configured_enterprise_root()))


def _enterprise_discard(arguments: ToolArguments) -> MutationRequest:
    from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

    root = _configured_enterprise_root()
    pending_remote = enterprise_sync_state.load(root).is_pending()
    return MutationRequest("enterprise_discard", DiscardWrite(root, pending_remote=pending_remote))


def _maintenance(arguments: ToolArguments) -> MutationRequest:
    root = resolve_repo_root(repo_root=_repo_root_argument(arguments), repo_preset=None)
    return MutationRequest("maintenance", RepositoryWrite(root))


_ENGAGEMENT_ROW = MutationToolManifestRow(intents=("engagement_authoring",), build_request=_engagement_authoring)

MUTATION_TOOL_MANIFEST: dict[str, MutationToolManifestRow] = {
    "artifact_create_entity": _ENGAGEMENT_ROW,
    "artifact_add_connection": _ENGAGEMENT_ROW,
    "artifact_create_diagram": _ENGAGEMENT_ROW,
    "artifact_create_matrix": _ENGAGEMENT_ROW,
    "artifact_create_document": _ENGAGEMENT_ROW,
    "artifact_edit_document": _ENGAGEMENT_ROW,
    "artifact_delete_document": _ENGAGEMENT_ROW,
    "artifact_edit_entity": _ENGAGEMENT_ROW,
    "artifact_edit_connection": _ENGAGEMENT_ROW,
    "artifact_edit_diagram": _ENGAGEMENT_ROW,
    "artifact_edit_connection_associations": _ENGAGEMENT_ROW,
    "artifact_delete_entity": _ENGAGEMENT_ROW,
    "artifact_delete_diagram": _ENGAGEMENT_ROW,
    "artifact_group": _ENGAGEMENT_ROW,
    "artifact_viewpoint": _ENGAGEMENT_ROW,
    "artifact_bulk_write": _ENGAGEMENT_ROW,
    "artifact_bulk_delete": _ENGAGEMENT_ROW,
    "artifact_promote_to_enterprise": MutationToolManifestRow(intents=("promotion",), build_request=_promotion),
    "artifact_save_changes": MutationToolManifestRow(
        intents=("engagement_authoring", "enterprise_save"), build_request=_save_changes
    ),
    "artifact_submit_for_review": MutationToolManifestRow(
        intents=("enterprise_submit",), build_request=_enterprise_submit
    ),
    "artifact_withdraw_changes": MutationToolManifestRow(
        intents=("enterprise_discard",), build_request=_enterprise_discard
    ),
    "artifact_admin_reindex": MutationToolManifestRow(intents=("maintenance",), build_request=_maintenance),
}

# Write-server tools that perform no architecture-repository mutation.
NON_MUTATING_WRITE_TOOLS: frozenset[str] = frozenset(
    {"artifact_help", "artifact_authoring_guidance", "artifact_get_operation"}
)



def register_mutation_tool(
    mcp: FastMCP,
    fn: Callable[..., object],
    *,
    name: str,
    title: str,
    description: str,
    annotations: object,
    structured_output: bool = True,
) -> None:
    """Register *fn* as a mutating tool. Refuses registration without a manifest row."""
    row = MUTATION_TOOL_MANIFEST.get(name)
    if row is None:
        raise LookupError(
            f"No mutation manifest row for tool {name!r} — every mutating MCP tool must "
            "declare its intent and target extraction in MUTATION_TOOL_MANIFEST before it can register."
        )
    signature = inspect.signature(fn)

    @wraps(fn)
    async def executed(*args: object, **kwargs: object) -> object:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        request = row.build_request(bound.arguments)
        if request.intent not in row.intents:
            raise RuntimeError(f"Tool {name!r} built undeclared intent {request.intent!r}.")
        future = mutation_executor().submit(request, lambda: fn(*args, **kwargs), operation_name=name)
        return await asyncio.wrap_future(future)

    executed.__mutation_manifest_name__ = name  # type: ignore[attr-defined]
    mcp.tool(
        name=name,
        title=title,
        description=description,
        annotations=annotations,  # type: ignore[arg-type]
        structured_output=structured_output,
    )(executed)
