"""Shared data types and small utilities for C4 diagram resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.domain.ontology_representation.artifact_types import ConnectionRecord

# Short, direction-consistent C4 edge labels per ArchiMate interaction type.
# Projected (model-backed) C4 edges use these verbs rather than prose description.
#
# Serving and association have no entry, and that is the point. Both say only "there is a
# dependency here", which is what the arrow already says: labelling them printed the word "uses"
# thirty-four times on one diagram and fifty-nine words on another, none of which a reader could
# have learned anything from. A label is for what the arrow cannot show. Where an author states one
# — the `edge_labels` override the renderer takes — it is used whatever the type.
_C4_CONN_LABELS: dict[str, str] = {
    "archimate-flow": "flows to",
    "archimate-triggering": "triggers",
    "archimate-access": "accesses",
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
    #: Items drawn *inside* this one. Only a deployment view fills it — a container is drawn inside
    #: the node that holds its artifact — and every other level leaves it empty.
    children: tuple["_ResolvedItem", ...] = ()
    #: Whether the model *declares* this a store, rather than a keyword in its technology hinting so.
    #: Shape inference reads the technology string for "sqlite", "postgres" and the like, which
    #: answers for a database and not for a file store — C4 counts a file system as a data store, and
    #: "Git VCS, File System Service" matches no keyword. The declaration outranks the guess.
    is_store: bool = False


@dataclass(frozen=True)
class _C4Connection:
    src_alias: str
    tgt_alias: str
    label: str
    artifact_id: str | None = None


@dataclass(frozen=True)
class _ResolvedState:
    """What one C4 diagram draws, after resolving whichever mode it was authored in.

    `scope_items` is a tuple rather than one item because a system landscape is about several
    systems at once and no one of them is the subject. The other four levels resolve exactly one,
    and `scope_item` is how they read it — a boundary can only wrap one thing, so the render modes
    divide along the same line: `node` draws each scope item, `boundary` wraps the single one.
    """

    scope_items: tuple[_ResolvedItem, ...]
    scope_render_mode: str
    internal_items: list[_ResolvedItem] = field(default_factory=list)
    outside_items: list[_ResolvedItem] = field(default_factory=list)
    connections: tuple[_C4Connection, ...] = ()
    entity_ids: tuple[str, ...] = ()
    connection_artifact_ids: tuple[str, ...] = ()

    @property
    def scope_item(self) -> _ResolvedItem:
        """The single scope, for the four levels that have one — and the first of a landscape's."""
        return self.scope_items[0]


def _alias_for(item_type: str, local_id: str, index: int = 0) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", local_id)
    prefix = "".join(p[:1].upper() for p in item_type.replace("-", "_").split("_")) or "C"
    return f"{prefix}_{normalized}_{index}"


def _normalize_alias(alias: str) -> str:
    return alias.strip().replace("-", "_")


def _conn_label(conn: ConnectionRecord) -> str:
    return _C4_CONN_LABELS.get(conn.conn_type, "")
