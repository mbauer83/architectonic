"""Style-rule evaluation for one placed entity/connection occurrence:
declaration-order first-match-wins per capability, ``applies_to`` type/specialization
scoping, half-open range bands, and ``default_style`` fallback. Relational styling (a
``mode="match"`` rule whose criteria contain an ``IncidentConnectionCondition``) is not a
separate mechanism — it falls out of reusing ``evaluate_entity_criteria``/
``evaluate_connection_criteria`` unchanged.

Callers (the projection service) are responsible for the "occlusion dominates styling"
invariant: this module always computes a style map from ``styling_rules``; it is the
caller's job to discard it when an occurrence carries exclusion reasons.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_criteria import ConnectionCriteriaGroup, EntityCriteriaGroup
from src.domain.viewpoints.viewpoint_criteria_evaluation import evaluate_connection_criteria, evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_projection import StyleRuleOutcome, StyleRuleOutcomeKind
from src.domain.viewpoints.viewpoint_scale_styling import ScaleBounds, StyleValue, _scale_value
from src.domain.viewpoints.viewpoints import PresentationSpec, RangeBand, StyleRule

ItemKind = Literal["entity", "connection"]
Item = EntityRecord | ConnectionRecord


@dataclass(frozen=True)
class RuleItemHit:
    """One rule's engagement with one item: ``matched`` (the rule's own predicate/value
    held, so it WOULD style the item) and ``applied`` (it actually styled it — false when
    a higher-precedence rule had already claimed the capability). The gap between the two
    is what lets callers report a rule as shadowed rather than silently inert."""

    rule_index: int
    matched: bool
    applied: bool


@dataclass(frozen=True)
class ItemStyleEvaluation:
    style: Mapping[str, StyleValue]
    schema_drift: frozenset[str]
    rule_hits: tuple[RuleItemHit, ...]


def _item_tags(item: Item, item_kind: ItemKind) -> frozenset[str]:
    # An item's tags are its type plus EVERY applied specialization (§15.2), so a style rule
    # whose `applies_to` names any one of them matches — not only the primary.
    if item_kind == "connection":
        assert isinstance(item, ConnectionRecord)
        return frozenset({item.conn_type, *item.specializations}) - {""}
    assert isinstance(item, EntityRecord)
    return frozenset({item.artifact_type, *item.specializations}) - {""}


def _match_outcome(
    rule: StyleRule, item: Item, item_kind: ItemKind, *, read_access: CriteriaReadAccess, registries: RegistrySnapshot
) -> tuple[bool, frozenset[str]]:
    if rule.match_criteria is None:
        return False, frozenset()
    if item_kind == "entity":
        assert isinstance(rule.match_criteria, EntityCriteriaGroup)
        assert isinstance(item, EntityRecord)
        outcome = evaluate_entity_criteria(rule.match_criteria, item, read_access=read_access, registries=registries)
    else:
        assert isinstance(rule.match_criteria, ConnectionCriteriaGroup)
        assert isinstance(item, ConnectionRecord)
        outcome = evaluate_connection_criteria(
            rule.match_criteria, item, read_access=read_access, registries=registries
        )
    return outcome.matched, outcome.schema_drift


def _endpoints_match(
    rule: StyleRule,
    connection: ConnectionRecord,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
) -> tuple[bool, frozenset[str]]:
    """Endpoint sub-criteria gate for edge rules: BOTH declared endpoint criteria must
    match their endpoint entity. A missing endpoint record fails the gate — an edge whose
    endpoint cannot be read never silently counts as matching a boundary predicate."""
    drift: set[str] = set()
    for criteria, entity_id in (
        (rule.source_criteria, connection.source),
        (rule.target_criteria, connection.target),
    ):
        if criteria is None:
            continue
        record = read_access.get_entity(entity_id)
        if record is None:
            return False, frozenset(drift)
        outcome = evaluate_entity_criteria(criteria, record, read_access=read_access, registries=registries)
        drift |= outcome.schema_drift
        if not outcome.matched:
            return False, frozenset(drift)
    return True, frozenset(drift)


def _band_for(value: object, bands: tuple[RangeBand, ...]) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    for band in bands:
        if (band.minimum is None or value >= band.minimum) and (band.maximum is None or value < band.maximum):
            return band.value
    return None


def _range_token(
    rule: StyleRule,
    item: Item,
    context: CriteriaContext,
    *,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment,
) -> tuple[str | None, frozenset[str]]:
    if rule.range_attribute is None:
        return None, frozenset()
    declared = resolve_attribute_path(rule.range_attribute, context=context, registries=registries)
    if declared is None:
        return None, frozenset({rule.range_attribute})
    value, present = read_attribute_value(item, rule.range_attribute, context=context, environment=environment)
    if not present:
        return None, frozenset()
    return _band_for(value, rule.range_bands), frozenset()


def _unresolvable_reference(
    rule: StyleRule, *, registries: RegistrySnapshot, declared_derived_names: frozenset[str]
) -> str | None:
    """The rule's attribute reference when it cannot resolve — a ``derived.<name>`` whose
    name the query never declares, or a schema path the registries don't know."""
    attribute = rule.scale_attribute if rule.mode == "scale" else rule.range_attribute if rule.mode == "range" else None
    if attribute is None:
        return None
    if attribute.startswith("derived."):
        return attribute if attribute.removeprefix("derived.") not in declared_derived_names else None
    context: CriteriaContext = "connection" if rule.capability.startswith("edge_") else "entity"
    return attribute if resolve_attribute_path(attribute, context=context, registries=registries) is None else None


def classify_style_rule_outcomes(
    presentation: PresentationSpec | None,
    hits: Iterable[RuleItemHit],
    *,
    registries: RegistrySnapshot,
    declared_derived_names: frozenset[str],
) -> tuple[StyleRuleOutcome, ...]:
    """Exactly one observable outcome per authored style rule (the "no silent no-op"
    contract): ``unresolvable`` beats the count-based kinds because an unresolvable
    reference styling nothing is a defect, not a legitimately empty match set."""
    if presentation is None:
        return ()
    matched: Counter[int] = Counter()
    applied: Counter[int] = Counter()
    for hit in hits:
        if hit.matched:
            matched[hit.rule_index] += 1
        if hit.applied:
            applied[hit.rule_index] += 1
    outcomes: list[StyleRuleOutcome] = []
    for index, rule in enumerate(presentation.styling_rules):
        detail = _unresolvable_reference(rule, registries=registries, declared_derived_names=declared_derived_names)
        if rule.disabled:
            kind: StyleRuleOutcomeKind = "disabled"
            detail = None
        elif detail is not None:
            kind = "unresolvable"
        elif applied[index] > 0:
            kind = "applied"
        elif matched[index] > 0:
            kind = "shadowed"
        else:
            kind = "expected-empty"
        outcomes.append(
            StyleRuleOutcome(
                rule_index=index,
                capability=rule.capability,
                kind=kind,
                matched_count=matched[index],
                applied_count=applied[index],
                detail=detail,
            )
        )
    return tuple(outcomes)


def evaluate_item_style(
    item: Item,
    item_kind: ItemKind,
    presentation: PresentationSpec | None,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
    scale_bounds: Mapping[int, ScaleBounds],
) -> ItemStyleEvaluation:
    """Resolve every display capability for one occurrence. First match per capability
    wins the styling, but every applicable rule is still evaluated so its engagement is
    observable (``rule_hits``) — a rule outshadowed on every item must be reportable,
    never silently inert.

    ``scale_bounds`` is **required**, and it used to default to ``{}``. That default was not a neutral
    value: an empty bounds map makes `_scale_value` return ``None`` for every rule index, so a caller
    that simply forgot it got a projection in which the whole scale mode silently did nothing. One did
    forget, for a release — the artifact-local projection — and a viewpoint pinned to a diagram styled
    nothing while the same viewpoint executed against the repository styled correctly. Requiring it
    turns that class of omission into a type error.
    """
    if presentation is None:
        return ItemStyleEvaluation({}, frozenset(), ())
    context: CriteriaContext = item_kind
    tags = _item_tags(item, item_kind)
    resolved: dict[str, StyleValue] = {}
    decided: set[str] = set()
    drift: set[str] = set()
    hits: list[RuleItemHit] = []
    for index, rule in enumerate(presentation.styling_rules):
        # A capability is node-scoped or edge-scoped by the same `edge_` convention the
        # presentation validator enforces (an `edge_*` capability pairs with connection
        # criteria, every other capability with entity criteria). Only evaluate a rule
        # against the item kind it targets — otherwise a node rule's entity criteria would
        # be matched against a connection (and vice versa), which is both meaningless and,
        # for `mode='match'`, a criteria-kind mismatch.
        if rule.disabled:
            continue
        if rule.capability.startswith("edge_") != (item_kind == "connection"):
            continue
        if rule.applies_to and not (rule.applies_to & tags):
            continue
        if item_kind == "connection" and (rule.source_criteria is not None or rule.target_criteria is not None):
            assert isinstance(item, ConnectionRecord)
            endpoints_ok, endpoint_drift = _endpoints_match(
                rule, item, read_access=read_access, registries=registries
            )
            drift |= endpoint_drift
            if not endpoints_ok:
                hits.append(RuleItemHit(rule_index=index, matched=False, applied=False))
                continue
        matched = False
        style_value: StyleValue | None = None
        if rule.mode == "match":
            matched, rule_drift = _match_outcome(rule, item, item_kind, read_access=read_access, registries=registries)
            drift |= rule_drift
            style_value = rule.value if matched and rule.value is not None else None
            matched = style_value is not None
        elif rule.mode == "range":
            token, rule_drift = _range_token(
                rule, item, context, registries=registries, environment=environment
            )
            drift |= rule_drift
            style_value = token
            matched = token is not None
        else:
            value = _scale_value(
                rule, index, item, context, registries=registries, environment=environment, bounds=scale_bounds
            )
            style_value = value
            matched = value is not None
        applied = matched and rule.capability not in decided
        if applied and style_value is not None:
            resolved[rule.capability] = style_value
            decided.add(rule.capability)
        hits.append(RuleItemHit(rule_index=index, matched=matched, applied=applied))
    for capability, token in presentation.default_style.items():
        resolved.setdefault(capability, token)
    return ItemStyleEvaluation(resolved, frozenset(drift), tuple(hits))
