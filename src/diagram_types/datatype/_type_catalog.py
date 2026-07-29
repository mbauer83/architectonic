"""Datatype type catalog — discovery queries for classifier-typed attribute types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassifierInfo:
    type_id: str
    label: str
    kind: str
    scope: str
    host_diagram_id: str


@dataclass(frozen=True)
class TypeCatalogResult:
    generation: int
    primitives: list[str]
    classifiers: list[ClassifierInfo]
    next_cursor: str | None


def query_datatype_types(
    store: Any,
    primitive_names: list[str],
    *,
    query: str | None = None,
    scope: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    diagram_id: str | None = None,
) -> TypeCatalogResult:
    """Return primitives and available classifier types for attribute authoring."""
    generation: int = store.read_model_version().generation
    referencing_scope = _diagram_scope(store, diagram_id)
    classifiers: list[ClassifierInfo] = []
    for e in store.list_entities(artifact_type="classifier"):
        entity_scope = store.scope_for_path(e.path)
        if scope is not None and entity_scope != scope:
            continue
        if referencing_scope == "enterprise" and entity_scope != "enterprise":
            continue
        if query is not None and query.lower() not in e.name.lower():
            continue
        if kind is not None and kind != "classifier":
            continue
        classifiers.append(ClassifierInfo(
            type_id=e.artifact_id,
            label=e.name,
            kind="classifier",
            scope=entity_scope,
            host_diagram_id=e.host_diagram_id or "",
        ))
    classifiers.sort(key=lambda c: (0 if c.scope == "enterprise" else 1, c.label.lower()))
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    page = classifiers[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(classifiers) else None
    return TypeCatalogResult(
        generation=generation,
        primitives=list(primitive_names),
        classifiers=page,
        next_cursor=next_cursor,
    )


def _diagram_scope(store: Any, diagram_id: str | None) -> str:
    if diagram_id is None:
        return "unknown"
    diagram = store.get_diagram(diagram_id)
    return store.scope_for_path(diagram.path) if diagram is not None else "unknown"


def query_type_usages(store: Any, *, type_id: str) -> list[dict[str, str]]:
    """Return diagrams that reference type_id as a classifier attribute type."""
    return [
        {"diagram_id": r[0], "classifier_local_id": r[1], "attr_name": r[2]}
        for r in store.diagrams_referencing_type_id(type_id)
    ]
