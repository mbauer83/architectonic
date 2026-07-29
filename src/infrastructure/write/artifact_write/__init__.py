"""ERP model writer operations package.

This package is the tool/infrastructure side of deterministic writing.
The MCP server should depend on these modules, not embed the logic.
"""

from ._diagram_edge_labels import set_diagram_edge_label
from .connection import add_connection
from .connection_edit import edit_connection, edit_connection_associations, remove_connection
from .diagram import create_diagram
from .diagram_delete import delete_diagram
from .diagram_edit import edit_diagram
from .diagram_sync import refresh_diagram, sync_diagram_to_model
from .document import create_document, delete_document, edit_document
from .entity import create_entity
from .entity_delete import delete_entity
from .entity_edit import edit_entity, promote_entity
from .help import write_help
from .matrix import create_matrix
from .type_guidance import get_type_guidance
from .types import SyncDiagramToModelResult, WriteResult

__all__ = [
    "SyncDiagramToModelResult",
    "WriteResult",
    "write_help",
    "create_entity",
    "edit_entity",
    "delete_entity",
    "promote_entity",
    "add_connection",
    "edit_connection",
    "edit_connection_associations",
    "remove_connection",
    "create_diagram",
    "edit_diagram",
    "set_diagram_edge_label",
    "refresh_diagram",
    "sync_diagram_to_model",
    "delete_diagram",
    "create_matrix",
    "get_type_guidance",
    "create_document",
    "edit_document",
    "delete_document",
]
