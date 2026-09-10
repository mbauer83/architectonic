"""Admin-mode write operations — enterprise repository writes.

This module is the ONLY authorised path for writing to the enterprise repo.
It enforces the enterprise boundary via assert_enterprise_write_root at every
entry point.

Two authorities call it, and which of them may is decided by the intent its
call site passes to the mutation policy, never by this module. Admin authoring
comes through src/infrastructure/rest/routers/admin.py under
`enterprise_admin_authoring`. Submitting a proposed change comes through
change_submission under `enterprise_proposal`, from REST and from MCP alike —
which is the case B67 exists for, a deployment that is not in admin mode. It
was true that no MCP tool reached here, and the reason recorded was that the
enterprise repo is not an MCP tool's to write; the accurate rule is that it is
not an *engagement authoring* tool's to write, and a submission is not one.

The standard write functions (entity.py, connection.py, …) unconditionally
reject enterprise roots via assert_engagement_write_root and are not called here.
The admin operations call the shared formatting, verification, and commit logic
directly — the same layer those functions use — keeping the boundary check
entirely at the callsite level.

Implementations are grouped by artifact family in admin_entity_ops,
admin_connection_ops, admin_diagram_ops and admin_document_ops; this module
re-exports them as the stable import surface.

The document and diagram edits are *composed* from the engagement ones rather than
written again: those computations never depended on which repository they wrote,
and their one engagement-specific line — the root assertion — is now a parameter.
The entity edit is the reason. It was written twice, and the second copy silently
lost two of the fields the first accepted.
"""

from __future__ import annotations

from ._entity_edit_support import _UNSET
from .admin_connection_ops import admin_add_connection, admin_remove_connection
from .admin_diagram_ops import (
    _write_diagram_to_enterprise,
    admin_delete_diagram,
    admin_edit_diagram,
)
from .admin_document_ops import admin_edit_document
from .admin_entity_ops import admin_create_entity, admin_delete_entity, admin_edit_entity

__all__ = [
    "_UNSET",
    "_write_diagram_to_enterprise",
    "admin_add_connection",
    "admin_create_entity",
    "admin_delete_entity",
    "admin_delete_diagram",
    "admin_edit_diagram",
    "admin_edit_document",
    "admin_edit_entity",
    "admin_remove_connection",
]
