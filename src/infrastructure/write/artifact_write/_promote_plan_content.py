"""Docs and diagrams sub-plan helpers for plan_promotion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.infrastructure.write.artifact_write.promote_to_enterprise import (
    DiagramPromotionConflict,
    DocPromotionConflict,
)

if TYPE_CHECKING:
    from src.infrastructure.write.artifact_write._promote_planning import ClassifierIndexes


def plan_docs(
    document_ids: list[str] | None,
    repo: Any,
    registry: Any,
    already: list[str],
    warnings: list[str],
) -> tuple[list[str], list[DocPromotionConflict]]:
    from src.infrastructure.write.artifact_write.promote_to_enterprise import _normalize_name  # noqa: PLC0415

    docs_to_add: list[str] = []
    doc_conflicts: list[DocPromotionConflict] = []
    enterprise_doc_ids = registry.enterprise_document_ids()
    index: dict[tuple[str, str], Any] = {}
    for rec in repo.list_documents():
        if rec.artifact_id in enterprise_doc_ids:
            index[(rec.doc_type, _normalize_name(rec.title))] = rec
    for did in document_ids or []:
        doc = repo.get_document(did)
        if doc is None:
            warnings.append(f"Document not found: {did}")
            continue
        if did in enterprise_doc_ids:
            already.append(did)
            continue
        ent = index.get((doc.doc_type, _normalize_name(doc.title)))
        if ent is not None:
            doc_conflicts.append(DocPromotionConflict(
                engagement_id=did, enterprise_id=ent.artifact_id,
                doc_type=doc.doc_type, engagement_title=doc.title, enterprise_title=ent.title,
            ))
        else:
            docs_to_add.append(did)
    return docs_to_add, doc_conflicts


def _check_diagram_classifiers(
    diag: Any,
    indexes: "ClassifierIndexes",
    warnings: list[str],
) -> None:
    """Emit advisory warnings for datatype classifier name-clashes with enterprise."""
    de = diag.extra.get("diagram-entities") if hasattr(diag, "extra") else None
    if not isinstance(de, dict):
        return
    for clf in de.get("classifier") or []:
        if not isinstance(clf, dict):
            continue
        clf_id = str(clf.get("id") or "")
        clf_label = str(clf.get("label") or "")
        if not clf_id.startswith("CLF@"):
            continue
        if clf_id in indexes.by_id:
            continue  # same id — idempotent, no warning
        if clf_label:
            norm = clf_label.strip().lower()
            existing_id = indexes.by_name.get(norm)
            if existing_id is not None:
                warnings.append(
                    f"Advisory: classifier '{clf_label}' in {diag.artifact_id} "
                    f"matches enterprise classifier {existing_id} by name but has a different id "
                    "(non-blocking; review before publishing)"
                )


def plan_diagrams(
    diagram_ids: list[str] | None,
    repo: Any,
    registry: Any,
    already: list[str],
    warnings: list[str],
    *,
    classifier_indexes: "ClassifierIndexes | None" = None,
) -> tuple[list[str], list[DiagramPromotionConflict]]:
    from src.infrastructure.write.artifact_write.promote_to_enterprise import _normalize_name  # noqa: PLC0415

    diags_to_add: list[str] = []
    diagram_conflicts: list[DiagramPromotionConflict] = []
    enterprise_diag_ids = registry.enterprise_diagram_ids()
    index: dict[tuple[str, str], Any] = {}
    for rec in repo.list_diagrams():
        if rec.artifact_id in enterprise_diag_ids:
            index[(rec.diagram_type, _normalize_name(rec.name))] = rec
    for did in diagram_ids or []:
        diag = repo.get_diagram(did)
        if diag is None:
            warnings.append(f"Diagram not found: {did}")
            continue
        if did in enterprise_diag_ids:
            already.append(did)
            continue
        ent = index.get((diag.diagram_type, _normalize_name(diag.name)))
        if ent is not None:
            diagram_conflicts.append(DiagramPromotionConflict(
                engagement_id=did, enterprise_id=ent.artifact_id,
                diagram_type=diag.diagram_type, engagement_name=diag.name, enterprise_name=ent.name,
            ))
        else:
            diags_to_add.append(did)
        if classifier_indexes is not None and getattr(diag, "diagram_type", None) == "datatype":
            _check_diagram_classifiers(diag, classifier_indexes, warnings)
    return diags_to_add, diagram_conflicts
