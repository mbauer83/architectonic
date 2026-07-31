"""Response contracts for the connection surface.

A connection's identity is the single-segment composite ``{src}---{tgt}@@{type}`` — the same string
the read surface emits as ``artifact_id`` — so it is path-addressable like any other resource
without inventing an id for it.

Endpoint names, types and scopes ride along with each row rather than being looked up per
connection: every surface that lists connections renders both ends, and a client resolving them
itself would issue one request per row against data the server already had in hand.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionSummary(_Closed):
    """One connection, with both endpoints resolved.

    ``gar_artifact_id`` appears only when the target was reached through a global-artifact
    reference: ``target`` is then the enterprise entity the reference stands for, and this is the
    reference itself — a client that needs to edit the proxy rather than the referent needs both.
    """

    artifact_id: str
    source: str
    target: str
    conn_type: str
    version: str
    status: str
    path: str
    content_text: str
    associated_entities: list[str]
    src_multiplicity: str | None = None
    tgt_multiplicity: str | None = None
    specialization: str | None = None
    specializations: list[str] = []
    metadata: dict[str, Any] = {}
    source_name: str
    target_name: str
    gar_artifact_id: str | None = None


class ConnectionListResponse(_Closed):
    """Connections matching the filters, as a page-shaped object rather than a bare array.

    An object leaves room for the pagination the house convention uses, and a top-level array has
    nowhere to put a total or a cursor without becoming a breaking change later.
    """

    items: list[ConnectionSummary]


class BrokenReferenceAction(_Closed):
    """One remedial action the cleanup would take, or took."""

    action: str
    path: str
    artifact_id: str | None = None
    detail: str | None = None


class BrokenReferenceCleanupResponse(_Closed):
    """What the cleanup found, and what it did about it.

    A global-artifact reference is broken when the enterprise entity it points to no longer exists.
    ``dry_run`` is echoed rather than assumed: the same body shape reports a plan and a result, and
    a caller reading a plan as a result would believe files had changed.
    """

    dry_run: bool
    broken_grfs: list[str]
    actions: list[BrokenReferenceAction]
    executed: bool
    errors: list[str]
