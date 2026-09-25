"""model_write_ops.py — Compatibility facade.

The implementation is split into smaller modules under src/tools/model_write/.
This module exists as a stable import path for MCP server code and tests.
"""

from typing import Literal

from src.application.modeling.artifact_write import DiagramConnectionInferenceMode
from src.domain.icons.normalised_icon import IconRefused
from src.infrastructure.write.artifact_write import (
    IconInUseError,
    IconUpload,
    SyncDiagramToModelResult,
    WriteResult,
    add_connection,
    create_diagram,
    create_document,
    create_entity,
    create_icon,
    create_matrix,
    delete_diagram,
    delete_document,
    delete_entity,
    delete_icon,
    edit_connection,
    edit_diagram,
    edit_document,
    edit_entity,
    edit_icon,
    get_type_guidance,  # filter, diagram_type, target
    promote_entity,
    refresh_diagram,
    remove_connection,
    rendered_membership,
    replace_icon,
    set_diagram_edge_label,
    sync_diagram_to_model,
    upload_from_base64,
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
    "rendered_membership",
    "refresh_diagram",
    "sync_diagram_to_model",
    "delete_diagram",
    "create_matrix",
    "create_document",
    "edit_document",
    "delete_document",
    "IconUpload",
    "create_icon",
    "delete_icon",
    "edit_icon",
    "replace_icon",
    "IconInUseError",
    "upload_from_base64",
    "IconRefused",
]
