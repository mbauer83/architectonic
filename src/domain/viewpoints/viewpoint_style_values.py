"""Style-value vocabulary for presentation styling, per display capability.

Color-bearing capabilities accept a semantic token, a named scale endpoint, or an
explicit ``#rrggbb`` color literal rendered as-is. Visual-token capabilities (shape,
icon, edge emphasis) accept only the semantic tokens their fixed notations are keyed
on. Every other capability (e.g. table ``badges``, whose value is displayed literally)
stays free-form. A value outside its capability's domain is a save-time validation
error — a value no renderer understands must never be accepted and then silently
painted as the neutral fallback.
"""

from __future__ import annotations

import re

SEMANTIC_STYLE_TOKENS: frozenset[str] = frozenset({"emphasis", "positive", "caution", "critical", "neutral"})
"""Fixed capability-agnostic vocabulary usable by every style mode."""

SCALE_ENDPOINT_TOKENS: frozenset[str] = frozenset({"heat-near", "heat-far", "heat-low", "heat-high"})
"""Named gradient endpoints for ``mode="scale"`` rules: the distance pair
(``heat-near``/``heat-far``) and the magnitude pair (``heat-low``/``heat-high``)."""

STYLE_VALUE_TOKENS: frozenset[str] = SEMANTIC_STYLE_TOKENS | SCALE_ENDPOINT_TOKENS

COLOR_CAPABILITIES: frozenset[str] = frozenset({"node_color", "edge_color", "cluster_grouping", "cell_emphasis"})
"""Capabilities whose value resolves to a solid color (or a color gradient in scale mode)."""

TOKEN_CAPABILITIES: frozenset[str] = frozenset({"node_shape", "node_icon", "edge_emphasis"})
"""Capabilities whose value selects one of a fixed notation set keyed on the semantic tokens."""

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_hex_color(value: str) -> bool:
    """True for an explicit ``#rrggbb`` color literal."""
    return _HEX_COLOR.match(value) is not None


def is_valid_style_value(capability: str, value: str) -> bool:
    """True when *value* lies in *capability*'s value domain (free-form capabilities
    accept anything)."""
    if capability in COLOR_CAPABILITIES:
        return value in STYLE_VALUE_TOKENS or is_hex_color(value)
    if capability in TOKEN_CAPABILITIES:
        return value in SEMANTIC_STYLE_TOKENS
    return True


def style_value_error(capability: str, value: str) -> str:
    if capability in TOKEN_CAPABILITIES:
        tokens = ", ".join(sorted(SEMANTIC_STYLE_TOKENS))
        return f"unknown style value {value!r} for {capability!r}: expected one of {tokens}"
    tokens = ", ".join(sorted(STYLE_VALUE_TOKENS))
    return f"unknown style value {value!r} for {capability!r}: expected one of {tokens}, or a '#rrggbb' color"


NEUTRAL_STYLE_VALUE = "neutral"
"""Replacement for out-of-vocabulary values authored before per-capability validation:
renderers painted every unknown value as the neutral fallback, so normalizing to
``neutral`` preserves exactly what such a definition already displayed."""
