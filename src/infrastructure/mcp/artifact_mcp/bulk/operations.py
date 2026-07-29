"""Operation-registry access for bulk MCP tools."""

from __future__ import annotations

from typing import Any

from src.infrastructure.write.operation_registry import operation_registry


def artifact_get_operation(*, operation_id: str) -> dict[str, Any]:
    record = operation_registry.get(operation_id)
    if record is None:
        raise ValueError(f"Unknown operation_id '{operation_id}'")
    return record
