"""Shared data types and small utilities for C4 diagram resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Short, direction-consistent C4 edge labels per ArchiMate interaction type.
# Projected (model-backed) C4 edges use these verbs rather than prose description.
_C4_CONN_LABELS: dict[str, str] = {
    "archimate-serving": "uses",
    "archimate-flow": "flows to",
    "archimate-triggering": "triggers",
    "archimate-access": "accesses",
    "archimate-association": "uses",
}


@dataclass(frozen=True)
class _ResolvedItem:
    local_id: str
    item_type: str
    alias: str
    label: str
    description: str
    technology: str
    external: bool
    entity_id: str | None = None  # set in standalone when item maps to a model entity
    shape: str | None = None      # explicit shape override (WU-E7); None = tech inference


@dataclass(frozen=True)
class _C4Connection:
    src_alias: str
    tgt_alias: str
    label: str
    artifact_id: str | None = None


@dataclass(frozen=True)
class _ResolvedState:
    scope_item: _ResolvedItem
    scope_render_mode: str
    internal_items: list[_ResolvedItem] = field(default_factory=list)
    outside_items: list[_ResolvedItem] = field(default_factory=list)
    connections: tuple[_C4Connection, ...] = ()
    entity_ids: tuple[str, ...] = ()
    connection_artifact_ids: tuple[str, ...] = ()


def _alias_for(item_type: str, local_id: str, index: int = 0) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", local_id)
    prefix = "".join(p[:1].upper() for p in item_type.replace("-", "_").split("_")) or "C"
    return f"{prefix}_{normalized}_{index}"


def _normalize_alias(alias: str) -> str:
    return alias.strip().replace("-", "_")


def _conn_label(conn: Any) -> str:
    return _C4_CONN_LABELS.get(conn.conn_type, "uses")
