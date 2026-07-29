"""Normalization of presentation style values authored before per-capability validation.

Style values used to be opaque strings; renderers painted anything they did not
recognize as the neutral fallback. Validation now rejects out-of-vocabulary values at
save time, so a definition carrying them could no longer be re-saved unchanged. This
module rewrites exactly those values to ``neutral`` — reproducing what they already
rendered as — and reports every replacement, so upgrade tooling can migrate a catalog
without changing its visible behavior.
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.viewpoints.viewpoint_style_values import NEUTRAL_STYLE_VALUE, is_valid_style_value
from src.domain.viewpoints.viewpoints import PresentationSpec, StyleRule, ViewpointDefinition


def _normalized(capability: str, value: str, label: str, replaced: list[str]) -> str:
    if is_valid_style_value(capability, value):
        return value
    replaced.append(f"{label}: {value!r}")
    return NEUTRAL_STYLE_VALUE


def _normalize_rule(rule: StyleRule, index: int, replaced: list[str]) -> StyleRule:
    label = f"styling_rules[{index}]"
    value = (
        _normalized(rule.capability, rule.value, f"{label}.value", replaced)
        if rule.value is not None
        else None
    )
    bands = tuple(
        replace(band, value=_normalized(rule.capability, band.value, f"{label}.range_bands[{position}]", replaced))
        for position, band in enumerate(rule.range_bands)
    )
    tokens = tuple(
        _normalized(rule.capability, token, f"{label}.scale_tokens[{position}]", replaced)
        for position, token in enumerate(rule.scale_tokens)
    )
    return replace(rule, value=value, range_bands=bands, scale_tokens=tokens)


def normalize_presentation_style_values(
    presentation: PresentationSpec,
) -> tuple[PresentationSpec, tuple[str, ...]]:
    """``(normalized_spec, replaced)`` — every style value outside its capability's
    domain rewritten to ``neutral``; ``replaced`` labels each rewritten value."""
    replaced: list[str] = []
    rules = tuple(_normalize_rule(rule, index, replaced) for index, rule in enumerate(presentation.styling_rules))
    defaults = {
        capability: _normalized(capability, value, f"default_style.{capability}", replaced)
        for capability, value in presentation.default_style.items()
    }
    if not replaced:
        return presentation, ()
    return replace(presentation, styling_rules=rules, default_style=defaults), tuple(replaced)


def normalize_definition_style_values(
    definition: ViewpointDefinition,
) -> tuple[ViewpointDefinition, tuple[str, ...]]:
    """Definition-level wrapper around ``normalize_presentation_style_values``."""
    if definition.presentation is None:
        return definition, ()
    presentation, replaced = normalize_presentation_style_values(definition.presentation)
    if not replaced:
        return definition, ()
    return replace(definition, presentation=presentation), replaced
