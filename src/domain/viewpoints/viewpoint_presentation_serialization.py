"""Serialize a ``presentation:`` block back to the Appendix-A canonical form — the
counterpart to ``viewpoint_presentation_parsing.py``."""

from __future__ import annotations

from typing import Any

from src.domain.viewpoints.viewpoint_criteria import ConnectionCriteriaGroup
from src.domain.viewpoints.viewpoint_criteria_serialization import (
    connection_criteria_group_to_mapping,
    entity_criteria_group_to_mapping,
)
from src.domain.viewpoints.viewpoints import ColumnSpec, PresentationSpec, RangeBand, StyleRule


def _column_to_mapping(column: ColumnSpec) -> dict[str, Any]:
    return {"label": column.label, "source": column.source}


def _range_band_to_mapping(band: RangeBand) -> dict[str, Any]:
    return {"minimum": band.minimum, "maximum": band.maximum, "value": band.value}


def _style_rule_to_mapping(rule: StyleRule) -> dict[str, Any]:
    result: dict[str, Any] = {"capability": rule.capability}
    if rule.applies_to:
        result["applies_to"] = sorted(rule.applies_to)
    if rule.mode != "match":
        result["mode"] = rule.mode
    if rule.mode == "match":
        if rule.match_criteria is not None:
            result["match_criteria"] = (
                connection_criteria_group_to_mapping(rule.match_criteria)
                if isinstance(rule.match_criteria, ConnectionCriteriaGroup)
                else entity_criteria_group_to_mapping(rule.match_criteria)
            )
        if rule.value is not None:
            result["value"] = rule.value
    else:
        if rule.mode == "scale":
            if rule.scale_attribute is not None:
                result["scale_attribute"] = rule.scale_attribute
            if rule.scale_min is not None:
                result["scale_min"] = rule.scale_min
            if rule.scale_max is not None:
                result["scale_max"] = rule.scale_max
            if rule.scale_tokens:
                result["scale_tokens"] = list(rule.scale_tokens)
        elif rule.range_attribute is not None:
            result["range_attribute"] = rule.range_attribute
        if rule.mode == "range" and rule.range_bands:
            result["range_bands"] = [_range_band_to_mapping(b) for b in rule.range_bands]
    if rule.source_criteria is not None:
        result["source_criteria"] = entity_criteria_group_to_mapping(rule.source_criteria)
    if rule.target_criteria is not None:
        result["target_criteria"] = entity_criteria_group_to_mapping(rule.target_criteria)
    if rule.disabled:
        result["disabled"] = True
    return result


def presentation_to_mapping(presentation: PresentationSpec) -> dict[str, Any]:
    result: dict[str, Any] = {"representation": presentation.representation}
    if presentation.display_options:
        result["display_options"] = dict(presentation.display_options)
    if presentation.columns is not None:
        result["columns"] = [_column_to_mapping(c) for c in presentation.columns]
    if presentation.row_by is not None:
        result["row_by"] = presentation.row_by
    if presentation.column_by is not None:
        result["column_by"] = presentation.column_by
    if presentation.row_criteria is not None:
        result["row_criteria"] = entity_criteria_group_to_mapping(presentation.row_criteria)
    if presentation.column_criteria is not None:
        result["column_criteria"] = entity_criteria_group_to_mapping(presentation.column_criteria)
    if presentation.group_by is not None:
        result["group_by"] = presentation.group_by
    if presentation.styling_rules:
        result["styling_rules"] = [_style_rule_to_mapping(r) for r in presentation.styling_rules]
    if presentation.default_style:
        result["default_style"] = dict(presentation.default_style)
    if presentation.target_types is not None:
        result["target_types"] = list(presentation.target_types)
    if presentation.legibility_budget is not None:
        result["legibility_budget"] = presentation.legibility_budget
    if presentation.aggregate_by is not None:
        result["aggregate_by"] = presentation.aggregate_by
    return result
