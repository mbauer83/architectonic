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

SCALE_ENDPOINT_ORDER: tuple[str, ...] = ("heat-near", "heat-far", "heat-low", "heat-high")
"""Named gradient endpoints for ``mode="scale"`` rules, **in the order they are offered**: the
distance pair (``heat-near``/``heat-far``) then the magnitude pair (``heat-low``/``heat-high``), each
pair's near end first.

A sequence rather than a set, because that order is information an author reads — the pairs group, and
within a pair the low end comes first — and a set cannot carry it. It lived in a JavaScript object
literal by accident of how palettes were written there; asking that literal for the palette instead
scrambled the offer into alphabetical, which is how this came to be declared properly."""

SCALE_ENDPOINT_TOKENS: frozenset[str] = frozenset(SCALE_ENDPOINT_ORDER)
"""Membership, derived from the order rather than restated beside it."""

STYLE_VALUE_TOKENS: frozenset[str] = SEMANTIC_STYLE_TOKENS | SCALE_ENDPOINT_TOKENS

#: What each token is actually painted as. One table, and the reason it is here rather than in a
#: surface adapter is that there is now more than one adapter.
#:
#: A token was opaque to domain code while every renderer of it was a browser: the GUI resolved
#: tokens to colour and the domain only had to say which tokens exist. An ad-hoc reading lens renders
#: **server-side** — it may re-layout, and it must export to SVG and PNG — so the diagram renderer is
#: a surface adapter too, and a second table in Python is exactly the shape this repository already
#: paid for: `DOMAIN_COLORS` is generated from the server because "three hardcoded palettes disagreed
#: on every domain".
#:
#: So the same arrangement, in the same direction: declared here, generated into the frontend's
#: constants by `tools/ontology/generate_types.py`, and read by `viewpointStyleTokens.ts` rather than
#: restated there. What stays true is the contract that mattered — a `StyleRule.value` is an opaque
#: token, and *nothing* interprets one except an adapter asking this table.
STYLE_TOKEN_COLORS: dict[str, str] = {
    "emphasis": "#2563eb",
    "positive": "#16a34a",
    "caution": "#d97706",
    "critical": "#dc2626",
    "neutral": "#6b7280",
    "heat-near": "#0891b2",
    "heat-far": "#dc2626",
    "heat-low": "#fbbf24",
    "heat-high": "#dc2626",
}

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
