"""model_write_ops.py — Compatibility facade.

The implementation is split into smaller modules under src/tools/model_write/.
This module exists as a stable import path for MCP server code and tests.
"""

from typing import Literal

from src.application.modeling.artifact_write import DiagramConnectionInferenceMode
from src.infrastructure.write.artifact_write import (
    SyncDiagramToModelResult,
    WriteResult,
    add_connection,
    create_diagram,
    create_document,
    create_entity,
    create_matrix,
    delete_diagram,
    delete_document,
    delete_entity,
    edit_connection,
    edit_diagram,
    edit_document,
    edit_entity,
    get_type_guidance,  # filter, diagram_type, target
    promote_entity,
    refresh_diagram,
    remove_connection,
    set_diagram_edge_label,
    sync_diagram_to_model,
    write_help,
)

WriteRepoScope = Literal["engagement"]

__all__ = [
    "DiagramConnectionInferenceMode",
    "SyncDiagramToModelResult",
    "WriteRepoScope",
    "WriteResult",
    "write_help",
    "get_type_guidance",
    "create_entity",
    "edit_entity",
    "delete_entity",
    "promote_entity",
    "add_connection",
    "edit_connection",
    "remove_connection",
    "create_diagram",
    "edit_diagram",
    "set_diagram_edge_label",
    "refresh_diagram",
    "sync_diagram_to_model",
    "delete_diagram",
    "create_matrix",
    "create_document",
    "edit_document",
    "delete_document",
]
