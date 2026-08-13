"""WU-1.4 acceptance: TypeResolver — scope/status-aware type resolution.

Acceptance criteria:
- primitive by name (module-declared): Resolved
- unknown primitive name: Unresolved("unknown-primitive")
- classifier by id found in projection: Resolved with classifier label
- missing classifier id: Unresolved("missing-id")
- enterprise diagram, engagement classifier: Unresolved("out-of-scope")
- engagement diagram, enterprise classifier: Resolved (cross-scope ok)
- baselined diagram, draft classifier: Unresolved("status-violation")
- baselined diagram, active classifier: Resolved
- custom primitive (classifier kind == "primitive") resolved by name
- label_for falls back to id when not in projection
"""

from __future__ import annotations

import pytest

from src.diagram_types.datatype._projection import (
    ClassifierDefinition,
    DatatypeVerificationProjection,
)
from src.diagram_types.datatype._type_resolver import Resolved, TypeResolver, Unresolved

_PRIMITIVE_NAMES: frozenset[str] = frozenset(
    ["String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"]
)

_RESOLVER = TypeResolver(_PRIMITIVE_NAMES)


def _proj(
    classifiers: list[ClassifierDefinition] | None = None,
) -> DatatypeVerificationProjection:
    by_id = {c.type_id: c for c in (classifiers or [])}
    by_name: dict[str, tuple[str, ...]] = {}
    for c in (classifiers or []):
        norm = c.label.lower().strip()
        by_name[norm] = by_name.get(norm, ()) + (c.type_id,)
    return DatatypeVerificationProjection(
        classifiers_by_id=by_id,
        classifier_ids_by_name=by_name,
        usages_by_id={},
    )


def _clf(
    type_id: str = "CLF@1.ab.order",
    label: str = "Order",
    kind: str = "class",
    scope: str = "engagement",
    status: str = "active",
    host_diagram_id: str = "DT-A",
) -> ClassifierDefinition:
    return ClassifierDefinition(
        type_id=type_id,
        label=label,
        kind=kind,
        scope=scope,
        status=status,
        host_diagram_id=host_diagram_id,
    )


# ---------------------------------------------------------------------------
# Primitive resolution
# ---------------------------------------------------------------------------


def test_resolve_declared_primitive() -> None:
    proj = _proj()
    result = _RESOLVER.resolve({"kind": "primitive", "name": "String"}, "engagement", proj)
    assert result == Resolved(label="String")


def test_resolve_all_declared_primitives() -> None:
    proj = _proj()
    for name in _PRIMITIVE_NAMES:
        assert isinstance(
            _RESOLVER.resolve({"kind": "primitive", "name": name}, "engagement", proj),
            Resolved,
        )


def test_unknown_primitive_returns_unresolved() -> None:
    proj = _proj()
    result = _RESOLVER.resolve({"kind": "primitive", "name": "Blob"}, "engagement", proj)
    assert isinstance(result, Unresolved)
    assert result.reason == "unknown-primitive"


# ---------------------------------------------------------------------------
# Classifier resolution
# ---------------------------------------------------------------------------


def test_resolve_classifier_by_id() -> None:
    clf = _clf(type_id="CLF@1.ab.order", label="Order")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": "CLF@1.ab.order"}, "engagement", proj
    )
    assert result == Resolved(label="Order")


def test_missing_classifier_id_returns_unresolved() -> None:
    proj = _proj()
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": "CLF@9.zz.missing"}, "engagement", proj
    )
    assert isinstance(result, Unresolved)
    assert result.reason == "missing-id"


def test_empty_id_returns_unresolved() -> None:
    proj = _proj()
    result = _RESOLVER.resolve({"kind": "classifier", "id": ""}, "engagement", proj)
    assert isinstance(result, Unresolved)
    assert result.reason == "missing-id"


# ---------------------------------------------------------------------------
# Scope rules (§2.3)
# ---------------------------------------------------------------------------


def test_engagement_diagram_resolves_enterprise_classifier() -> None:
    """engagement → engagement + enterprise."""
    clf = _clf(scope="enterprise")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id}, "engagement", proj
    )
    assert isinstance(result, Resolved)


def test_engagement_diagram_resolves_engagement_classifier() -> None:
    clf = _clf(scope="engagement")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id}, "engagement", proj
    )
    assert isinstance(result, Resolved)


def test_enterprise_diagram_rejects_engagement_classifier() -> None:
    """enterprise → enterprise only; engagement classifiers out-of-scope."""
    clf = _clf(scope="engagement")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id}, "enterprise", proj
    )
    assert isinstance(result, Unresolved)
    assert result.reason == "out-of-scope"


def test_enterprise_diagram_resolves_enterprise_classifier() -> None:
    clf = _clf(scope="enterprise")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id}, "enterprise", proj
    )
    assert isinstance(result, Resolved)


# ---------------------------------------------------------------------------
# Status conformity
# ---------------------------------------------------------------------------


def test_baselined_diagram_rejects_draft_classifier() -> None:
    clf = _clf(status="draft")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id},
        "engagement",
        proj,
        referencing_diagram_status="baselined",
    )
    assert isinstance(result, Unresolved)
    assert result.reason == "status-violation"


def test_baselined_diagram_accepts_active_classifier() -> None:
    clf = _clf(status="active")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id},
        "engagement",
        proj,
        referencing_diagram_status="baselined",
    )
    assert isinstance(result, Resolved)


def test_draft_diagram_accepts_draft_classifier() -> None:
    clf = _clf(status="draft")
    proj = _proj([clf])
    result = _RESOLVER.resolve(
        {"kind": "classifier", "id": clf.type_id},
        "engagement",
        proj,
        referencing_diagram_status="draft",
    )
    assert isinstance(result, Resolved)


# ---------------------------------------------------------------------------
# Custom primitives (§D16 — classifier kind == "primitive" resolved by name)
# ---------------------------------------------------------------------------


def test_custom_primitive_resolved_by_name() -> None:
    custom_prim = _clf(
        type_id="CLF@1.ab.money", label="Money", kind="primitive", scope="engagement"
    )
    proj = _proj([custom_prim])
    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "Money"}, "engagement", proj
    )
    assert result == Resolved(label="Money")


def test_custom_primitive_case_insensitive() -> None:
    custom_prim = _clf(
        type_id="CLF@1.ab.money", label="Money", kind="primitive", scope="engagement"
    )
    proj = _proj([custom_prim])
    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "money"}, "engagement", proj
    )
    assert isinstance(result, Resolved)


def test_custom_primitive_out_of_scope() -> None:
    """Enterprise diagram cannot resolve an engagement custom primitive."""
    custom_prim = _clf(
        type_id="CLF@1.ab.money", label="Money", kind="primitive", scope="engagement"
    )
    proj = _proj([custom_prim])
    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "Money"}, "enterprise", proj
    )
    assert isinstance(result, Unresolved)
    assert result.reason == "out-of-scope"


# ---------------------------------------------------------------------------
# Two declarations, one label — the promotion case
# ---------------------------------------------------------------------------


def _shadowed_pair(engagement_first: bool) -> DatatypeVerificationProjection:
    """One label declared twice: an engagement copy and the enterprise one it shadows.

    The pair is built in both orders because the defect *was* the order: the scan walked
    `classifiers_by_id` as the dictionary happened to iterate, so which declaration answered a
    reference depended on which was inserted first.
    """
    engagement = _clf(
        type_id="CLF@1.eng.money", label="Money", kind="primitive", scope="engagement"
    )
    enterprise = _clf(
        type_id="CLF@1.ent.money", label="Money", kind="primitive", scope="enterprise"
    )
    return _proj([engagement, enterprise] if engagement_first else [enterprise, engagement])


@pytest.mark.parametrize("engagement_first", [True, False])
def test_an_enterprise_diagram_resolves_the_enterprise_declaration_whichever_was_declared_first(
    engagement_first: bool,
) -> None:
    """The defect: an engagement declaration found first answered `out-of-scope` for a reference
    the enterprise declaration standing behind it satisfies — so the answer, and the stated
    reason, depended on dictionary order."""
    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "Money"}, "enterprise", _shadowed_pair(engagement_first)
    )

    assert result == Resolved(label="Money")


@pytest.mark.parametrize("engagement_first", [True, False])
def test_an_engagement_diagram_resolves_it_too_whichever_was_declared_first(
    engagement_first: bool,
) -> None:
    """An engagement diagram may use either, so it always resolves — the point is that it does so
    identically whichever order the two arrived in."""
    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "Money"}, "engagement", _shadowed_pair(engagement_first)
    )

    assert result == Resolved(label="Money")


def test_a_refusal_names_the_declaration_that_was_really_in_the_way() -> None:
    """With nothing usable, the reason comes from the best-ranked candidate rather than from
    whichever was met first, so it describes a declaration that really did refuse."""
    draft_enterprise = _clf(
        type_id="CLF@1.ent.money", label="Money", kind="primitive",
        scope="enterprise", status="draft",
    )
    proj = _proj([draft_enterprise])

    result = _RESOLVER.resolve(
        {"kind": "primitive", "name": "Money"}, "enterprise", proj,
        referencing_diagram_status="baselined",
    )

    assert result == Unresolved("status-violation")


def test_a_classifier_that_is_not_a_primitive_does_not_answer_a_primitive_reference() -> None:
    """The label index is shared with every classifier kind, so the kind filter has to survive
    the move onto it."""
    same_label_class = _clf(
        type_id="CLF@1.ab.money", label="Money", kind="class", scope="engagement"
    )
    proj = _proj([same_label_class])

    result = _RESOLVER.resolve({"kind": "primitive", "name": "Money"}, "engagement", proj)

    assert isinstance(result, Unresolved)
    assert result.reason == "unknown-primitive"


# ---------------------------------------------------------------------------
# label_for
# ---------------------------------------------------------------------------


def test_label_for_known_id() -> None:
    clf = _clf(type_id="CLF@1.ab.order", label="Order")
    proj = _proj([clf])
    assert _RESOLVER.label_for("CLF@1.ab.order", proj) == "Order"


def test_label_for_unknown_id_falls_back_to_id() -> None:
    proj = _proj()
    assert _RESOLVER.label_for("CLF@9.zz.missing", proj) == "CLF@9.zz.missing"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_non_dict_type_ref_returns_missing_id() -> None:
    proj = _proj()
    result = _RESOLVER.resolve("not-a-dict", "engagement", proj)
    assert isinstance(result, Unresolved)
    assert result.reason == "missing-id"


def test_unknown_kind_returns_missing_id() -> None:
    proj = _proj()
    result = _RESOLVER.resolve({"kind": "exotic"}, "engagement", proj)
    assert isinstance(result, Unresolved)
    assert result.reason == "missing-id"
