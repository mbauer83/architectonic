"""Compatibility wrapper for split bulk MCP tools."""

from src.infrastructure.mcp.artifact_mcp.bulk import (
    artifact_bulk_delete,
    artifact_bulk_write,
    artifact_get_operation,
    register,
)

__all__ = [
    "artifact_bulk_delete",
    "artifact_bulk_write",
    "artifact_get_operation",
    "register",
]
