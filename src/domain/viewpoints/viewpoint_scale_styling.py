"""Scale-mode style rules: deterministic bounds from the complete selected result
set, per-item scale positions, and the rule-level schema-drift contract (drift
means the attribute resolves in NO context — a mixed entity+connection
population never reports drift for an attribute its entities resolve)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_condition_validation import (
    CriteriaContext,
    RegistrySnapshot,
    resolve_attribute_path,
)
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationEnvironment
from src.domain.viewpoints.viewpoints import PresentationSpec, StyleRule

ItemKind = Literal["entity", "connection"]
Item = EntityRecord | ConnectionRecord


def _item_tags(item: Item, item_kind: ItemKind) -> frozenset[str]:
    # Type plus EVERY applied specialization (§15.2): a scale whose `applies_to` names any
    # one of a concept's specializations matches it, not only the primary.
    if item_kind == "connection":
        assert isinstance(item, ConnectionRecord)
        return frozenset({item.conn_type, *item.specializations}) - {""}
    assert isinstance(item, EntityRecord)
    return frozenset({item.artifact_type, *item.specializations}) - {""}


@dataclass(frozen=True)
class ScaleStyleValue:
    """Adapter-facing scale result: interpolate between tokens at ``position``."""

    position: float
    tokens: tuple[str, str]


StyleValue = str | ScaleStyleValue


@dataclass(frozen=True)
class ScaleBounds:
    minimum: float
    maximum: float


@dataclass(frozen=True)
class ScaleLegend:
    capability: str
    attribute: str
    minimum: float
    maximum: float
    tokens: tuple[str, str]



def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return float(value.date().toordinal())
    if isinstance(value, date):
        return float(value.toordinal())
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                return float(date.fromisoformat(value).toordinal())
            except ValueError:
                return None
    return None


def _scale_bound(value: float | str | None) -> float | None:
    return _number(value) if value is not None else None


def calculate_scale_bounds(
    presentation: PresentationSpec | None,
    items: tuple[tuple[Item, ItemKind], ...],
    *,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment,
) -> tuple[Mapping[int, ScaleBounds], tuple[ScaleLegend, ...], frozenset[str]]:
    """Calculate deterministic bounds from the complete selected result set."""
    if presentation is None:
        return {}, (), frozenset()
    bounds: dict[int, ScaleBounds] = {}
    legends: list[ScaleLegend] = []
    drift: set[str] = set()
    for index, rule in enumerate(presentation.styling_rules):
        if rule.disabled or rule.mode != "scale" or rule.scale_attribute is None or len(rule.scale_tokens) != 2:
            continue
        # Drift is a rule-level statement ("this attribute resolves nowhere"), not a
        # per-item one: a mixed entity+connection population must not report drift
        # merely because an entity-schema attribute doesn't resolve in the
        # connection context — those items are simply outside the rule's reach.
        entity_resolvable = (
            resolve_attribute_path(rule.scale_attribute, context="entity", registries=registries) is not None
        )
        connection_resolvable = (
            resolve_attribute_path(rule.scale_attribute, context="connection", registries=registries) is not None
        )
        if (
            not entity_resolvable
            and not connection_resolvable
            and not rule.scale_attribute.startswith("derived.")
        ):
            drift.add(rule.scale_attribute)
        values: list[float] = []
        for item, kind in items:
            if rule.applies_to and not (rule.applies_to & _item_tags(item, kind)):
                continue
            context: CriteriaContext = kind
            if not (entity_resolvable if context == "entity" else connection_resolvable):
                continue
            value, present = read_attribute_value(
                item, rule.scale_attribute, context=context, environment=environment
            )
            numeric = _number(value) if present else None
            if numeric is not None:
                values.append(numeric)
        minimum = _scale_bound(rule.scale_min)
        maximum = _scale_bound(rule.scale_max)
        if minimum is None and values:
            minimum = min(values)
        if maximum is None and values:
            maximum = max(values)
        if minimum is None or maximum is None:
            continue
        tokens = (rule.scale_tokens[0], rule.scale_tokens[1])
        bounds[index] = ScaleBounds(minimum=minimum, maximum=maximum)
        legends.append(
            ScaleLegend(
                capability=rule.capability,
                attribute=rule.scale_attribute,
                minimum=minimum,
                maximum=maximum,
                tokens=tokens,
            )
        )
    return bounds, tuple(legends), frozenset(drift)


def _scale_value(
    rule: StyleRule,
    index: int,
    item: Item,
    context: CriteriaContext,
    *,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment,
    bounds: Mapping[int, ScaleBounds],
) -> ScaleStyleValue | None:
    if rule.scale_attribute is None or len(rule.scale_tokens) != 2 or index not in bounds:
        return None
    # Same schema-drift contract as every other comparator/style path: an attribute path
    # the registries don't know (and isn't a derived. path, which bypasses schema lookup
    # by design) is treated as absent, not read straight off raw extra data.
    if (
        not rule.scale_attribute.startswith("derived.")
        and resolve_attribute_path(rule.scale_attribute, context=context, registries=registries) is None
    ):
        return None
    value, present = read_attribute_value(item, rule.scale_attribute, context=context, environment=environment)
    numeric = _number(value) if present else None
    if numeric is None:
        return None
    scale = bounds[index]
    # Out-of-range values saturate at the nearest endpoint (standard heat-map behavior)
    # rather than dropping out of the scale entirely — an item beyond the declared bounds
    # still reads as "far"/"near", never as unstyled.
    clamped = min(max(numeric, scale.minimum), scale.maximum)
    position = 0.0 if scale.maximum == scale.minimum else (clamped - scale.minimum) / (scale.maximum - scale.minimum)
    return ScaleStyleValue(position=position, tokens=(rule.scale_tokens[0], rule.scale_tokens[1]))


