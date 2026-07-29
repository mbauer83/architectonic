"""Bulk MCP write/delete tools split into focused modules."""

from .delete import artifact_bulk_delete
from .operations import artifact_get_operation
from .register import register
from .write import artifact_bulk_write

__all__ = [
    "artifact_bulk_delete",
    "artifact_bulk_write",
    "artifact_get_operation",
    "register",
]
