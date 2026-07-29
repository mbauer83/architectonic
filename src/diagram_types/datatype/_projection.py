"""WU-1.3: DatatypeVerificationProjection compiler.

Builds a read-only cross-diagram view of all classifier definitions and
attribute-type usages from a CandidateRepository. Compiled only from
CandidateRepository reads — no SQLite direct access.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any, Mapping

from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


@dataclass(frozen=True)
class ClassifierDefinition:
    """A classifier known to the workspace at verification time."""

    type_id: str
    label: str
    kind: str
    scope: str
    status: str
    host_diagram_id: str


@dataclass(frozen=True)
class AttributeTypeUsage:
    """One attribute on one classifier that references a classifier type by id."""

    diagram_id: str
    classifier_local_id: str
    attr_name: str


@dataclass(frozen=True)
class DatatypeVerificationProjection:
    """Cross-diagram projection used by E332/W333 and other datatype rules."""

    classifiers_by_id: Mapping[str, ClassifierDefinition]
    classifier_ids_by_name: Mapping[str, tuple[str, ...]]
    usages_by_id: Mapping[str, tuple[AttributeTypeUsage, ...]]


def compile_projection(
    candidate: Any,
    ctx: BaseDiagramVerificationContext,
) -> DatatypeVerificationProjection:
    """Compile a DatatypeVerificationProjection from *candidate* and the diagram under test.

    Classifiers come from two sources, the second taking precedence so a diagram always
    resolves references to its own classifiers (the same-write contract) even before it is
    committed to the candidate view:
      1. committed / candidate classifiers (cross-diagram resolution), and
      2. the classifiers declared inline in the diagram being verified (``ctx.fm``).

    candidate is typed Any to avoid cross-layer imports (it satisfies CandidateRepository).
    """
    classifiers_by_id: dict[str, ClassifierDefinition] = {}
    for entity in candidate.list_entities(artifact_type="classifier"):
        extra: dict[str, Any] = dict(entity.extra) if entity.extra else {}
        classifiers_by_id[entity.artifact_id] = ClassifierDefinition(
            type_id=entity.artifact_id,
            label=entity.name,
            kind=str(extra.get("classifier_kind") or ""),
            scope=str(candidate.scope_for_path(entity.path)),
            status=entity.status,
            host_diagram_id=str(entity.host_diagram_id or ""),
        )
    for clf_def in _inline_classifier_defs(ctx):
        committed = classifiers_by_id.get(clf_def.type_id)
        if committed is not None and clf_def.label == clf_def.type_id:
            # Inline classifier omitted an explicit label (managed_fields: label falls back to
            # the bound model entity name) — preserve the committed/binding-derived label.
            clf_def = replace(clf_def, label=committed.label)
        classifiers_by_id[clf_def.type_id] = clf_def

    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for clf in classifiers_by_id.values():
        norm_name = clf.label.lower().strip()
        if norm_name:
            name_to_ids[norm_name].append(clf.type_id)

    usages_raw: dict[str, list[AttributeTypeUsage]] = defaultdict(list)
    seen_diagram_ids: set[str] = set()
    for diagram in candidate.list_diagrams(diagram_type="datatype"):
        seen_diagram_ids.add(diagram.artifact_id)
        extra_d: dict[str, Any] = dict(diagram.extra) if diagram.extra else {}
        _collect_usages(diagram.artifact_id, extra_d.get("diagram-entities"), usages_raw)
    own_id = str(ctx.fm.get("artifact-id") or "")
    if own_id and own_id not in seen_diagram_ids:
        _collect_usages(own_id, ctx.fm.get("diagram-entities"), usages_raw)

    return DatatypeVerificationProjection(
        classifiers_by_id=classifiers_by_id,
        classifier_ids_by_name={name: tuple(ids) for name, ids in name_to_ids.items()},
        usages_by_id={k: tuple(v) for k, v in usages_raw.items()},
    )


def _inline_classifier_defs(ctx: BaseDiagramVerificationContext) -> Iterator[ClassifierDefinition]:
    """ClassifierDefinitions for the classifiers declared in the diagram under verification."""
    de = ctx.fm.get("diagram-entities")
    classifiers = de.get("classifier") if isinstance(de, dict) else None
    own_id = str(ctx.fm.get("artifact-id") or "")
    status = str(ctx.fm.get("status") or "")
    for clf in classifiers if isinstance(classifiers, list) else []:
        if not isinstance(clf, dict):
            continue
        clf_id = str(clf.get("id") or "")
        if not clf_id:
            continue
        yield ClassifierDefinition(
            type_id=clf_id,
            label=str(clf.get("label") or clf_id),
            kind=str(clf.get("classifier_kind") or ""),
            scope=str(ctx.scope),
            status=status,
            host_diagram_id=own_id,
        )


def _collect_usages(
    diagram_id: str,
    de: Any,
    usages_raw: dict[str, list[AttributeTypeUsage]],
) -> None:
    """Append every classifier-typed attribute usage found in *de* to *usages_raw*."""
    classifiers = de.get("classifier") if isinstance(de, dict) else None
    for clf in classifiers if isinstance(classifiers, list) else []:
        if not isinstance(clf, dict):
            continue
        clf_id = str(clf.get("id") or "")
        for attr in clf.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            type_ref = attr.get("type")
            if not isinstance(type_ref, dict) or type_ref.get("kind") != "classifier":
                continue
            ref_id = str(type_ref.get("id") or "")
            if ref_id:
                usages_raw[ref_id].append(AttributeTypeUsage(
                    diagram_id=diagram_id,
                    classifier_local_id=clf_id,
                    attr_name=str(attr.get("name") or ""),
                ))
