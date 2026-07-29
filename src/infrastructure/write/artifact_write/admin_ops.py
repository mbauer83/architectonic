"""Admin-mode write operations — enterprise repository writes.

This module is the ONLY authorised path for writing to the enterprise repo.
It is called exclusively from src/infrastructure/gui/routers/admin.py and never
from any MCP tool. It enforces the enterprise boundary via
assert_enterprise_write_root at every entry point.

The standard write functions (entity.py, connection.py, …) unconditionally
reject enterprise roots via assert_engagement_write_root and are not called here.
The admin operations call the shared formatting, verification, and commit logic
directly — the same layer those functions use — keeping the boundary check
entirely at the callsite level.

Implementations are grouped by artifact family in admin_entity_ops,
admin_connection_ops, and admin_diagram_ops; this module re-exports them as the
stable import surface.
"""

from __future__ import annotations

from ._entity_edit_support import _UNSET
from .admin_connection_ops import admin_add_connection, admin_remove_connection
from .admin_diagram_ops import _write_diagram_to_enterprise, admin_delete_diagram
from .admin_entity_ops import admin_create_entity, admin_delete_entity, admin_edit_entity

__all__ = [
    "_UNSET",
    "_write_diagram_to_enterprise",
    "admin_add_connection",
    "admin_create_entity",
    "admin_delete_entity",
    "admin_delete_diagram",
    "admin_edit_entity",
    "admin_remove_connection",
]
