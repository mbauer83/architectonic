"""Parsing for the ``presentation:`` block: representation, columns,
matrix axes, and style rules, Appendix-A canonical form. A style rule's ``match_criteria``
is entity or connection criteria depending on its capability (``edge_*`` => connection)."""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.viewpoints.viewpoint_criteria_parsing import (
    parse_connection_criteria_group,
    parse_entity_criteria_group,
)
from src.domain.viewpoints.viewpoints import (
    REPRESENTATION_CAPABILITIES,
    VALID_STYLE_CONDITION_MODES,
    ColumnSpec,
    PresentationSpec,
    RangeBand,
    Representation,
    StyleConditionMode,
    StyleRule,
)

_PRESENTATION_KEYS = frozenset(
    {
        "representation",
        "display_options",
        "columns",
        "row_by",
        "column_by",
        "row_criteria",
        "column_criteria",
        "group_by",
        "styling_rules",
        "default_style",
        "target_types",
        "legibility_budget",
        "aggregate_by",
    }
)
_COLUMN_KEYS = frozenset({"label", "source"})
_RANGE_BAND_KEYS = frozenset({"minimum", "maximum", "value"})
_STYLE_RULE_KEYS = frozenset(
    {
        "capability", "applies_to", "mode", "match_criteria", "range_attribute", "range_bands", "value",
        "scale_attribute", "scale_min", "scale_max", "scale_tokens",
        "source_criteria", "target_criteria", "disabled",
    }
)


def _require_representation(value: object, *, label: str) -> Representation:
    text = str(value)
    if text not in ("exploration", "table", "matrix", "diagram"):
        raise ValueError(f"{label}: representation {text!r} is not one of {sorted(REPRESENTATION_CAPABILITIES)}")
    return text


def _require_style_mode(value: object, *, label: str) -> StyleConditionMode:
    text = str(value)
    if text not in ("match", "range", "scale"):
        raise ValueError(f"{label}: mode {text!r} is not one of {sorted(VALID_STYLE_CONDITION_MODES)}")
    return text


def _column_from_mapping(raw: object, *, label: str) -> ColumnSpec:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label}: column must be a mapping")
    unknown = set(raw.keys()) - _COLUMN_KEYS
    if unknown:
        raise ValueError(f"{label}: column: unknown key(s) {sorted(unknown)}")
    return ColumnSpec(label=str(raw["label"]), source=str(raw["source"]))


def _range_band_from_mapping(raw: object, *, label: str) -> RangeBand:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label}: range band must be a mapping")
    unknown = set(raw.keys()) - _RANGE_BAND_KEYS
    if unknown:
        raise ValueError(f"{label}: range band: unknown key(s) {sorted(unknown)}")
    minimum = raw.get("minimum")
    maximum = raw.get("maximum")
    return RangeBand(
        minimum=float(minimum) if minimum is not None else None,
        maximum=float(maximum) if maximum is not None else None,
        value=str(raw["value"]),
    )


def _style_rule_from_mapping(raw: object, *, label: str) -> StyleRule:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label}: styling rule must be a mapping")
    unknown = set(raw.keys()) - _STYLE_RULE_KEYS
    if unknown:
        raise ValueError(f"{label}: styling rule: unknown key(s) {sorted(unknown)}")
    capability = str(raw["capability"])
    mode = _require_style_mode(raw.get("mode", "match"), label=label)
    applies_to = frozenset(str(v) for v in raw.get("applies_to", ()))
    source_criteria = (
        parse_entity_criteria_group(raw["source_criteria"]) if raw.get("source_criteria") is not None else None
    )
    target_criteria = (
        parse_entity_criteria_group(raw["target_criteria"]) if raw.get("target_criteria") is not None else None
    )
    disabled = bool(raw.get("disabled", False))
    if mode == "match":
        match_raw = raw.get("match_criteria")
        match_criteria = None
        if match_raw is not None:
            match_criteria = (
                parse_connection_criteria_group(match_raw)
                if capability.startswith("edge_")
                else parse_entity_criteria_group(match_raw)
            )
        return StyleRule(
            capability=capability,
            applies_to=applies_to,
            mode="match",
            match_criteria=match_criteria,
            value=str(raw["value"]) if raw.get("value") is not None else None,
            source_criteria=source_criteria,
            target_criteria=target_criteria,
            disabled=disabled,
        )
    if mode == "scale":
        tokens_raw = raw.get("scale_tokens", ())
        tokens = tuple(str(token) for token in tokens_raw) if isinstance(tokens_raw, (list, tuple)) else ()
        return StyleRule(
            capability=capability,
            applies_to=applies_to,
            mode="scale",
            scale_attribute=str(raw["scale_attribute"]) if raw.get("scale_attribute") else None,
            scale_min=_scale_bound(raw.get("scale_min")),
            scale_max=_scale_bound(raw.get("scale_max")),
            scale_tokens=tokens if len(tokens) == 2 else (),
            source_criteria=source_criteria,
            target_criteria=target_criteria,
            disabled=disabled,
        )
    range_attribute = raw.get("range_attribute")
    range_bands = tuple(_range_band_from_mapping(b, label=label) for b in raw.get("range_bands", ()))
    return StyleRule(
        capability=capability,
        applies_to=applies_to,
        mode="range",
        range_attribute=str(range_attribute) if range_attribute else None,
        range_bands=range_bands,
        source_criteria=source_criteria,
        target_criteria=target_criteria,
        disabled=disabled,
    )


def _scale_bound(value: object) -> float | str | None:
    if value is None or isinstance(value, (float, str)):
        return value
    if isinstance(value, int):
        return float(value)
    raise ValueError("scale bound must be numeric or an ISO date")


def presentation_from_mapping(raw: object, *, label: str) -> PresentationSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label}: presentation must be a mapping")
    unknown = set(raw.keys()) - _PRESENTATION_KEYS
    if unknown:
        raise ValueError(f"{label}: presentation: unknown key(s) {sorted(unknown)}")
    representation = _require_representation(raw.get("representation"), label=label)
    columns_raw = raw.get("columns")
    columns = (
        tuple(_column_from_mapping(c, label=label) for c in columns_raw)
        if isinstance(columns_raw, (list, tuple))
        else None
    )
    row_criteria_raw = raw.get("row_criteria")
    column_criteria_raw = raw.get("column_criteria")
    styling_raw = raw.get("styling_rules", ())
    display_options = raw.get("display_options")
    default_style = raw.get("default_style")
    return PresentationSpec(
        representation=representation,
        display_options=dict(display_options) if isinstance(display_options, Mapping) else {},
        columns=columns,
        row_by=str(raw["row_by"]) if raw.get("row_by") else None,
        column_by=str(raw["column_by"]) if raw.get("column_by") else None,
        row_criteria=parse_entity_criteria_group(row_criteria_raw) if row_criteria_raw is not None else None,
        column_criteria=parse_entity_criteria_group(column_criteria_raw) if column_criteria_raw is not None else None,
        group_by=str(raw["group_by"]) if raw.get("group_by") else None,
        styling_rules=tuple(_style_rule_from_mapping(r, label=label) for r in styling_raw)
        if isinstance(styling_raw, (list, tuple))
        else (),
        default_style={str(k): str(v) for k, v in default_style.items()} if isinstance(default_style, Mapping) else {},
        target_types=(
            tuple(str(t) for t in raw["target_types"])
            if isinstance(raw.get("target_types"), (list, tuple))
            else None
        ),
        legibility_budget=(
            int(budget_raw) if isinstance(budget_raw := raw.get("legibility_budget"), (int, float, str)) else None
        ),
        aggregate_by=str(raw["aggregate_by"]) if raw.get("aggregate_by") is not None else None,
    )
