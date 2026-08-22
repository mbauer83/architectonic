"""Datatype per-diagram verification contributions (E330/E331/E332/W333/E336).

Wraps datatype-specific checks as DiagramVerificationContributions so the
central verifier imports no datatype symbol directly.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


class _BackingConsistencyContribution:
    """E330/E331 — bidirectional dt-* backing consistency check."""

    diagnostic_codes: tuple[str, ...] = ("E330", "E331")

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        from src.application.verification._verifier_rules_datatype import (  # noqa: PLC0415
            check_datatype_backing_consistency,
        )
        if ctx.catalogs is None:
            return
        check_datatype_backing_consistency(
            ctx.fm,
            set(ctx.allowed_connections),
            ctx.catalogs.ontology,
            ctx.catalogs.diagram_types,
            result,
            ctx.loc,
        )


BACKING_CONSISTENCY_CONTRIBUTION = _BackingConsistencyContribution()


_CLF_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


class _AttributeTypeSchemaContribution:
    """E336 — each classifier attribute type ref must be a valid discriminated-union dict."""

    diagnostic_codes: tuple[str, ...] = ("E336",)

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        de: dict[str, Any] = ctx.fm.get("diagram-entities") or {}
        classifiers: list[Any] = de.get("classifier") or []
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415
        severity = Severity.ERROR if ctx.type_references_blocking else Severity.WARNING

        def emit(clf_id: str, attr_name: str, msg: str) -> None:
            full = f"Classifier '{clf_id}' attribute '{attr_name}': {msg}"
            result.issues.append(Issue(severity, "E336", full, ctx.loc))

        for clf in classifiers:
            if not isinstance(clf, dict):
                continue
            clf_id = str(clf.get("id") or "")
            attrs: list[Any] = clf.get("attributes") or []
            if not isinstance(attrs, list):
                continue
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                type_ref = attr.get("type")
                if type_ref is None:
                    continue
                attr_name = str(attr.get("name") or "")
                if not isinstance(type_ref, dict):
                    emit(clf_id, attr_name, f"'type' must be a tagged dict {{kind:…}}, got {type(type_ref).__name__}")
                    continue
                kind = type_ref.get("kind")
                if kind == "primitive":
                    pname = type_ref.get("name")
                    if not isinstance(pname, str) or not pname.strip():
                        emit(clf_id, attr_name, "primitive type must have non-empty 'name'")
                    if "id" in type_ref:
                        emit(clf_id, attr_name, "primitive type must not have 'id'")
                    extra = set(type_ref.keys()) - {"kind", "name"}
                    if extra:
                        emit(clf_id, attr_name, f"primitive type has unexpected keys: {sorted(extra)}")
                elif kind == "classifier":
                    eid = type_ref.get("id")
                    if not isinstance(eid, str) or not _CLF_ID_RE.match(eid):
                        emit(clf_id, attr_name, f"classifier type 'id' must match PREFIX@EPOCH.RANDOM.SLUG, got {eid!r}")  # noqa: E501
                    if "name" in type_ref:
                        emit(clf_id, attr_name, "classifier type must not have 'name'")
                    extra = set(type_ref.keys()) - {"kind", "id"}
                    if extra:
                        emit(clf_id, attr_name, f"classifier type has unexpected keys: {sorted(extra)}")
                else:
                    emit(clf_id, attr_name, f"'type.kind' must be 'primitive' or 'classifier', got {kind!r}")


ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION = _AttributeTypeSchemaContribution()


# ---------------------------------------------------------------------------
# E332 / W333 helpers (module-level pure functions)
# ---------------------------------------------------------------------------


def _iter_typed_attrs(
    classifiers: list[Any],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield (clf_id, attr_name, type_ref) for every well-formed typed attribute."""
    for clf in classifiers:
        if not isinstance(clf, dict):
            continue
        clf_id = str(clf.get("id") or "")
        for attr in clf.get("attributes") or []:
            if isinstance(attr, dict):
                type_ref = attr.get("type")
                if isinstance(type_ref, dict):
                    yield clf_id, str(attr.get("name") or ""), type_ref


def _e332_issue_or_none(
    clf_id: str,
    attr_name: str,
    type_ref: dict[str, Any],
    resolved: Any,
    loc: str,
    Issue: Any,
    severity: str,
) -> Any:
    """Return an E332 Issue if *resolved* is Unresolved, else None."""
    from src.diagram_types.datatype._type_resolver import Unresolved  # noqa: PLC0415

    if not isinstance(resolved, Unresolved):
        return None
    return Issue(
        severity,
        "E332",
        f"Classifier '{clf_id}' attribute '{attr_name}': type reference unresolved ({resolved.reason})",
        loc,
        details={
            "classifier": clf_id,
            "attr_name": attr_name,
            "type_ref": type_ref,
            "reason": resolved.reason,
            "candidates": list(resolved.candidates),
        },
    )


def _clf_in_scope(clf_scope: str, referencing_scope: str) -> bool:
    """True if a classifier with *clf_scope* is visible from *referencing_scope*."""
    return clf_scope == "enterprise" if referencing_scope == "enterprise" else True


def _w333_issue_or_none(
    clf_id: str,
    clf_def: Any,
    projection: Any,
    referencing_scope: str,
    loc: str,
    primitive_names: frozenset[str],
    Issue: Any,
    Severity: Any,
) -> Any:
    """Return a W333 Issue if the classifier's name collides, else None."""
    label = clf_def.label
    if not label:
        return None
    if label in primitive_names:
        return Issue(
            Severity.WARNING,
            "W333",
            f"Classifier '{clf_id}' name '{label}' collides with a built-in primitive type",
            loc,
        )
    norm = label.lower().strip()
    colliding = [
        other_id
        for other_id in projection.classifier_ids_by_name.get(norm, ())
        if other_id != clf_id
        and _clf_in_scope(projection.classifiers_by_id[other_id].scope, referencing_scope)
    ]
    return (
        Issue(
            Severity.WARNING,
            "W333",
            f"Classifier '{clf_id}' name '{label}' collides with in-scope classifier(s): {colliding}",
            loc,
        )
        if colliding
        else None
    )


# ---------------------------------------------------------------------------
# Projection-based contribution (E332 + W333)
# ---------------------------------------------------------------------------


class _ProjectionBasedContributions:
    """E332 + W333 — one DatatypeVerificationProjection compiled per diagram.

    E332: a well-formed type reference that does not resolve, or violates scope/status.
    W333: a classifier defined in the verified diagram whose normalized name collides
          with another in-scope classifier or a module primitive (advisory only).
    """

    diagnostic_codes: tuple[str, ...] = ("E332", "W333")

    def __init__(self, primitive_names: frozenset[str]) -> None:
        from src.diagram_types.datatype._type_resolver import TypeResolver  # noqa: PLC0415

        self._resolver = TypeResolver(primitive_names)
        self._primitive_names = primitive_names

    def run(self, candidate: Any, ctx: BaseDiagramVerificationContext, result: Any) -> None:
        from src.diagram_types.datatype._projection import compile_projection  # noqa: PLC0415
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415

        projection = compile_projection(candidate, ctx)
        de: dict[str, Any] = ctx.fm.get("diagram-entities") or {}
        classifiers: list[Any] = de.get("classifier") or []
        scope = ctx.scope
        status = str(ctx.fm.get("status") or "")
        type_severity = Severity.ERROR if ctx.type_references_blocking else Severity.WARNING

        result.issues.extend(filter(None, (
            _e332_issue_or_none(
                clf_id, attr_name, type_ref,
                self._resolver.resolve(type_ref, scope, projection, referencing_diagram_status=status),
                ctx.loc, Issue, type_severity,
            )
            for clf_id, attr_name, type_ref in _iter_typed_attrs(classifiers)
        )))

        result.issues.extend(filter(None, (
            _w333_issue_or_none(
                clf_id,
                projection.classifiers_by_id[clf_id],
                projection, scope, ctx.loc, self._primitive_names, Issue, Severity,
            )
            for clf in classifiers
            if isinstance(clf, dict)
            for clf_id in [str(clf.get("id") or "")]
            if clf_id and clf_id in projection.classifiers_by_id
        )))


# ---------------------------------------------------------------------------
# E334 — reference-impact (per-transaction)
# ---------------------------------------------------------------------------


def _find_classifier_usages(candidate: Any, type_id: str) -> list[tuple[str, str, str]]:
    """Return (diagram_id, clf_local_id, attr_name) for every attr in candidate referencing type_id."""
    usages: list[tuple[str, str, str]] = []
    for diagram in candidate.list_diagrams(diagram_type="datatype"):
        de = diagram.extra.get("diagram-entities")
        if not isinstance(de, dict):
            continue
        for clf in (de.get("classifier") or []):
            if not isinstance(clf, dict):
                continue
            clf_id = str(clf.get("id") or "")
            for attr in (clf.get("attributes") or []):
                if not isinstance(attr, dict):
                    continue
                tr = attr.get("type")
                if isinstance(tr, dict) and tr.get("kind") == "classifier" and tr.get("id") == type_id:
                    usages.append((diagram.artifact_id, clf_id, str(attr.get("name") or "")))
    return usages


class _ReferenceImpactContribution:
    """E334 — removed classifier still referenced by another diagram in the candidate transaction."""

    diagnostic_codes: tuple[str, ...] = ("E334",)

    def run(self, ctx: Any, result: Any) -> None:
        from src.domain.verification_findings import Issue, Severity  # noqa: PLC0415
        severity = Severity.ERROR if ctx.type_references_blocking else Severity.WARNING

        committed_ids = frozenset(e.artifact_id for e in ctx.committed.list_entities(artifact_type="classifier"))
        candidate_ids = frozenset(e.artifact_id for e in ctx.candidate.list_entities(artifact_type="classifier"))
        removed_ids = committed_ids - candidate_ids
        if not removed_ids:
            return
        for removed_id in sorted(removed_ids):
            usages = _find_classifier_usages(ctx.candidate, removed_id)
            if not usages:
                continue
            usage_str = "; ".join(f"{d}:{c}.{a}" for d, c, a in usages)
            result.issues.append(Issue(
                severity, "E334",
                f"Classifier '{removed_id}' removed while still referenced: {usage_str}",
                ctx.location,
                details={
                    "removed_id": removed_id,
                    "usages": [
                        {"diagram_id": d, "classifier_local_id": c, "attr_name": a}
                        for d, c, a in usages
                    ],
                },
            ))
