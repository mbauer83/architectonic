"""MCP tools for the local changes this repository is holding.

Editing an artifact the engagement does not own records a change against it instead of writing. An
agent editing promoted content needs the same two things a person does: to see what it is holding,
and to take one back. Without them a recorded change is something that happens to a session and
never appears again.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.application.modeling.change_overview import recorded_changes
from src.application.modeling.proposed_change import PENDING_STATES, PROPOSAL_STATE
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    repo_cached,
    resolve_repo_roots,
    roots_key,
)
from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, READ_ONLY

_LIST_DESCRIPTION = (
    "List the local changes this repository is holding: edits to artifacts promoted to the "
    "enterprise repository, which cannot be written here and are recorded as changes awaiting "
    "review. Each row names the artifact by name and by the local reference that stands for it — "
    "the enterprise id is what the change is against, not something this repository can open. "
    "\n\nstate: 'draft' has been put to nobody yet; 'submitted' is under review. "
    "\n\ncondition: 'stale' means the enterprise artifact has moved since the change was written; "
    "divergence then carries, per field, what the change asks for and what the artifact says now."
)

_DISCARD_DESCRIPTION = (
    "Take back a local change, naming it by its own artifact_id (from artifact_list_changes) — an "
    "artifact may carry more than one. The record is kept in a terminal state rather than deleted: "
    "a submitted change has been seen by someone, and its disappearance would be indistinguishable "
    "from it never having existed. A change that has already ended is refused, not re-ended."
)


def _repo_for(repo_root: str | None):  # noqa: ANN202 — the repository type is the caller's concern
    roots = resolve_repo_roots(
        repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None
    )
    return roots[0], repo_cached(roots_key(roots))


def artifact_list_changes(*, repo_root: str | None = None) -> dict[str, Any]:
    _root, repo = _repo_for(repo_root)
    return {
        "changes": [
            {
                "artifact_id": change.change_id,
                "target_id": change.target_id,
                "target_name": change.target_name,
                "kind": change.kind,
                "changed_fields": list(change.changed_fields),
                "state": change.state,
                "condition": change.condition,
                "divergence": [
                    {"field": d.field, "proposed": d.proposed, "current": d.current}
                    for d in change.divergence
                ],
            }
            for change in recorded_changes(repo)
        ]
    }


def artifact_discard_change(*, artifact_id: str, repo_root: str | None = None) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.proposal_lifecycle import mark_proposal_state

    root, repo = _repo_for(repo_root)
    record = repo.get_entity(artifact_id)
    if record is None:
        raise ValueError(f"There is no change '{artifact_id}' in this repository.")
    if str(record.extra.get(PROPOSAL_STATE, "")) not in PENDING_STATES:
        raise ValueError(
            f"'{artifact_id}' has already ended; a change that is integrated or abandoned is a "
            "record of what happened and is not changed again."
        )
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)
    discarded = mark_proposal_state(record.path, artifact_id=artifact_id, state="abandoned")
    if discarded:
        clear_repo_caches(record.path)
        mutation_context.finalize()
    return {"artifact_id": artifact_id, "discarded": discarded, "state": "abandoned"}


def register_change_read_tools(mcp: MCPServer) -> None:
    mcp.tool(
        name="artifact_list_changes",
        title="Artifact: List Local Changes",
        description=_LIST_DESCRIPTION,
        annotations=READ_ONLY,
        structured_output=True,
    )(artifact_list_changes)


def register_change_write_tools(mcp: MCPServer) -> None:
    register_mutation_tool(
        mcp,
        artifact_discard_change,
        name="artifact_discard_change",
        title="Artifact: Discard a Local Change",
        description=_DISCARD_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
    )
