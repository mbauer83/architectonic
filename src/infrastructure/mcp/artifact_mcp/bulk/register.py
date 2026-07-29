"""FastMCP registration for bulk write/delete tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.tool_annotations import (
    DESTRUCTIVE_LOCAL_WRITE,
    LOCAL_WRITE,
    READ_ONLY,
)

from .delete import artifact_bulk_delete
from .operations import artifact_get_operation
from .write import artifact_bulk_write


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_bulk_write,
        name="artifact_bulk_write",
        title="Artifact Write: Bulk Create/Edit",
        description=(
            "Batch entity creates, connection adds, and edits in one call. "
            "Items auto-sort (create_entity → add_connection → edits); submit in any order.\n"
            "op values: create_entity (artifact_type, name), "
            "add_connection (source_entity, connection_type, target_entity), "
            "edit_entity (artifact_id), "
            "edit_connection (source_entity, target_entity, connection_type, operation=update|remove). "
            "All other fields match the corresponding single-item tools.\n"
            "To connect entities created in the same batch: set '_ref':'<alias>' on the create_entity item, "
            "then use '$ref:<alias>' as source_entity or target_entity in add_connection — "
            "the backend substitutes the assigned artifact_id before processing connections.\n"
            "Optional auto_sync_diagrams=true reconciles affected diagrams after entity renames and "
            "connection removals before final verification.\n"
            "Returns one result per item (input order): op, artifact_id, wrote, verification, warnings?, error?. "
            "Each result includes operation_id. Optional idempotency_key reuses a prior completed result for the same "
            "logical batch. No file content in results. dry_run=true previews without writing. "
            "Accepts both full (PREFIX@epoch.random.slug) and short (PREFIX@epoch.random) artifact IDs."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_bulk_delete,
        name="artifact_bulk_delete",
        title="Artifact Write: Bulk Delete",
        description=(
            "Batch destructive operations with dependency-aware planning and final repository verification. "
            "Supported ops: delete_entity (artifact_id), "
            "delete_connection (source_entity, connection_type, target_entity), "
            "delete_document (artifact_id), delete_diagram (artifact_id). "
            "The batch is preflighted as a whole before any live deletes occur. "
            "Optional auto_sync_diagrams=true reconciles dependent diagrams instead of requiring "
            "explicit delete_diagram items when references become stale. Empty diagrams are removed. "
            "Connections are removed before dependent entity deletes; diagrams/documents are removed before entities; "
            "the tool returns per-item results plus a batch_verification summary and operation_id. "
            "Optional idempotency_key reuses a prior completed result for the same logical batch. "
            "Accepts both full (PREFIX@epoch.random.slug) and short (PREFIX@epoch.random) artifact IDs. "
            "Stages the whole batch in a repo copy and verifies before committing — for a single "
            "item with no cascade, artifact_delete_entity/artifact_delete_diagram/"
            "artifact_delete_document are cheaper (no full-repo staging copy)."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    mcp.tool(
        name="artifact_get_operation",
        title="Artifact Write: Get Operation Status",
        description=(
            "Return the latest recorded status, phase, timestamps, error, and final result for a prior "
            "bulk operation by operation_id."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )(artifact_get_operation)
