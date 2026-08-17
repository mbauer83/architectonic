"""Datatype type catalog — discovery queries for classifier-typed attribute types.

This is the answer an author picks a type from, so what it can distinguish is what they can choose
between. It reported `kind="classifier"` for every row and listed only the module's built-in scalars
under `primitives`, which made a repository's own `primitive`-kinded classifier — a declaration the
ontology accepts, the renderer stereotypes and the resolver resolves — indistinguishable here from a
structured type. It could still be selected, buried among the classifiers of whichever diagram
declared it, and it never read as the scalar it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.diagram_types.datatype._classifier_kinds import PRIMITIVE_KIND, classifier_kind_of


@dataclass(frozen=True)
class ClassifierInfo:
    type_id: str
    label: str
    #: What the declaration says this is — `class`, `datatype`, `enumeration` or `primitive`.
    #: A picker groups a `primitive` with the built-in scalars rather than with structured types.
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
        entity_kind = classifier_kind_of(e.extra or {})
        if kind is not None and kind != entity_kind:
            continue
        classifiers.append(ClassifierInfo(
            type_id=e.artifact_id,
            label=e.name,
            kind=entity_kind,
            scope=entity_scope,
            host_diagram_id=e.host_diagram_id or "",
        ))
    classifiers.sort(key=lambda c: (0 if c.scope == "enterprise" else 1, c.label.lower()))
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    page = classifiers[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(classifiers) else None
    return TypeCatalogResult(
        generation=generation,
        primitives=_primitive_vocabulary(primitive_names, classifiers),
        classifiers=page,
        next_cursor=next_cursor,
    )


def _primitive_vocabulary(
    declared: list[str], classifiers: list[ClassifierInfo]
) -> list[str]:
    """Every scalar type an attribute may name — the module's, then the repository's own.

    Whole-population rather than page-scoped, and deliberately: `primitives` is the vocabulary,
    not a page of it, and paging it beside the classifiers would make the set of scalars on offer
    depend on which page a picker happened to be holding.

    A custom primitive's *label* is what goes in, because that is what the built-in entries are and
    what an author reads. Selecting one still records the classifier reference the picker already
    emits, which is what survives a rename; nothing about the reference form changes here.
    """
    names = list(declared)
    for classifier in classifiers:
        if classifier.kind == PRIMITIVE_KIND and classifier.label not in names:
            names.append(classifier.label)
    return names


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
