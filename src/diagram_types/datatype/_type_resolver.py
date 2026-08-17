"""WU-1.4: TypeResolver — scope/status-aware attribute-type resolution.

Resolves a tagged attribute type reference (primitive or classifier) using
a DatatypeVerificationProjection. No SQLite or I/O; pure data transformation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.diagram_types.datatype._classifier_kinds import PRIMITIVE_KIND


@dataclass(frozen=True)
class Resolved:
    """A type reference that resolved successfully."""

    label: str


@dataclass(frozen=True)
class Unresolved:
    """A type reference that failed to resolve, with a machine-readable reason."""

    reason: str
    """One of: unknown-primitive, missing-id, out-of-scope, status-violation."""

    candidates: tuple[str, ...] = field(default_factory=tuple)
    """Suggested alternative classifier ids or primitive names, may be empty."""


class TypeResolver:
    """Resolve tagged type references using a compiled projection.

    Primitive names are the module-declared list (e.g. String, Integer) plus
    any in-scope classifiers whose kind is 'primitive' (custom primitives per §D16).
    """

    def __init__(self, primitive_names: frozenset[str]) -> None:
        self._primitive_names = primitive_names

    def resolve(
        self,
        type_ref: Any,
        referencing_scope: str,
        projection: Any,
        *,
        referencing_diagram_status: str = "",
    ) -> Resolved | Unresolved:
        """Resolve *type_ref* in the context of a diagram with *referencing_scope*.

        Args:
            type_ref: The raw attribute type dict — expected to have at least ``kind``.
            referencing_scope: ``"engagement"``, ``"enterprise"``, or ``"unknown"``
                (the repository scope of the diagram containing the reference).
            projection: A :class:`DatatypeVerificationProjection`.
            referencing_diagram_status: Status of the referencing diagram
                (e.g. ``"draft"``, ``"baselined"``). Used for status conformity.
        """
        if not isinstance(type_ref, dict):
            return Unresolved("missing-id")

        kind = type_ref.get("kind")

        if kind == "primitive":
            return self._resolve_primitive(
                type_ref, referencing_scope, projection, referencing_diagram_status
            )
        if kind == "classifier":
            return self._resolve_classifier(
                type_ref, referencing_scope, projection, referencing_diagram_status
            )
        return Unresolved("missing-id")

    def label_for(self, classifier_id: str, projection: Any) -> str:
        """Return the label for *classifier_id*, falling back to the id itself."""
        clf = projection.classifiers_by_id.get(classifier_id)
        if clf is None:
            return classifier_id
        return clf.label

    # ------------------------------------------------------------------

    def _resolve_primitive(
        self,
        type_ref: dict[str, Any],
        referencing_scope: str,
        projection: Any,
        referencing_diagram_status: str,
    ) -> Resolved | Unresolved:
        name = str(type_ref.get("name") or "")
        if not name:
            return Unresolved("unknown-primitive")

        # Module-declared primitive
        if name in self._primitive_names:
            return Resolved(label=name)

        # Custom primitive — a classifier with kind == "primitive" and this label.
        norm = name.lower().strip()
        declared = self._custom_primitives_named(norm, projection)
        if declared:
            return self._first_usable(declared, referencing_scope, referencing_diagram_status)

        # Suggest close matches from declared primitives
        candidates = tuple(
            p for p in sorted(self._primitive_names)
            if norm in p.lower()
        )
        return Unresolved("unknown-primitive", candidates=candidates)

    @staticmethod
    def _custom_primitives_named(norm: str, projection: Any) -> tuple[Any, ...]:
        """Every custom primitive carrying this label, enterprise first.

        Through `classifier_ids_by_name`, which the projection already builds and W333 already
        reads, rather than a second scan of the classifiers: a label index asked for by two
        callers is one index, and the scan it replaces walked in dictionary order.

        Enterprise first, and then by id: with two declarations sharing a label — an engagement one
        shadowing an enterprise one during a promotion — the order decided which was found, so a
        reference the enterprise declaration would have satisfied could be refused as out-of-scope
        depending on nothing but how the dictionary happened to iterate. The collision itself is
        W333's to report; this only has to stop resolution depending on it.

        `_type_catalog` sorts its page the same way and this deliberately does not share that key:
        one is presentation order and the other is resolution precedence. They agree today because
        the enterprise declaration is the more authoritative in both senses, not because they are
        one rule — and binding them would let a change to how a catalogue *reads* change which
        declaration a reference *resolves to*.
        """
        found = [
            clf
            for clf_id in projection.classifier_ids_by_name.get(norm, ())
            if (clf := projection.classifiers_by_id.get(clf_id)) is not None
            and clf.kind == PRIMITIVE_KIND
        ]
        return tuple(sorted(found, key=lambda clf: (0 if clf.scope == "enterprise" else 1, clf.type_id)))

    def _first_usable(
        self, declared: tuple[Any, ...], referencing_scope: str, referencing_diagram_status: str
    ) -> Resolved | Unresolved:
        """The first declaration this reference may actually use, or why the best one is refused.

        Refusing on the first *match* rather than the first *usable* match is what named the wrong
        cause: an engagement declaration found first answered `out-of-scope` while an enterprise
        one sat behind it, satisfying the very reference being refused. When none is usable the
        refusal comes from the highest-ranked candidate, so the message describes a declaration
        that really was in the way.
        """
        refusals: list[Unresolved] = []
        for clf in declared:
            refusal = self._check_scope(clf.scope, referencing_scope) or self._check_status(
                clf.status, referencing_diagram_status
            )
            if refusal is None:
                return Resolved(label=clf.label)
            refusals.append(refusal)
        return refusals[0]

    def _resolve_classifier(
        self,
        type_ref: dict[str, Any],
        referencing_scope: str,
        projection: Any,
        referencing_diagram_status: str,
    ) -> Resolved | Unresolved:
        clf_id = str(type_ref.get("id") or "")
        if not clf_id:
            return Unresolved("missing-id")

        clf = projection.classifiers_by_id.get(clf_id)
        if clf is None:
            return Unresolved("missing-id")

        scope_err = self._check_scope(clf.scope, referencing_scope)
        if scope_err is not None:
            return scope_err

        status_err = self._check_status(clf.status, referencing_diagram_status)
        if status_err is not None:
            return status_err

        return Resolved(label=clf.label)

    @staticmethod
    def _check_scope(clf_scope: str, referencing_scope: str) -> Unresolved | None:
        """Return an Unresolved if *clf_scope* is not visible from *referencing_scope*."""
        # enterprise diagrams may only reference enterprise classifiers
        if referencing_scope == "enterprise" and clf_scope == "engagement":
            return Unresolved("out-of-scope")
        return None

    @staticmethod
    def _check_status(clf_status: str, referencing_diagram_status: str) -> Unresolved | None:
        """Return an Unresolved if status conformity is violated."""
        # A baselined diagram may not reference a classifier whose host is draft
        if referencing_diagram_status == "baselined" and clf_status == "draft":
            return Unresolved("status-violation")
        return None
