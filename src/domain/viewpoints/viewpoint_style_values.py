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

from collections.abc import Sequence

from src.domain.hex_colors import is_hex_color, mix_colors

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

AD_HOC_RAMP_TOKENS: tuple[str, str] = ("heat-low", "heat-high")
"""The endpoints an *ad-hoc* reading ramps between, when a reader colours a diagram by an attribute
they picked rather than by an authored rule.

The magnitude pair, because that is the question a reader asks of an attribute they chose to colour
by — "where is this high" — and not the distance pair, which answers "how far is this from
something".

Declared here rather than in the lens that renders with it, because the reading panel has to draw the
same two swatches in its colour key: a key showing one gradient beside a picture drawn in another
would be worse than no key. Generated into the frontend constants for that reason."""

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

#: A qualitative sequence, for colouring by an attribute whose values are a bounded set with no
#: order — an enum, a boolean. Assigned by the member's position in the *declared* value order and
#: cycled if there are more members than colours, so the same member always takes the same colour on
#: every diagram and a reader can carry a reading from one picture to the next. Not hashed to a colour:
#: a hash is stable too, but it is stable at nothing a reader can predict, and neighbouring members
#: would land on neighbouring hues by accident as often as not.
#:
#: Eight, ordered so that any prefix of them stays distinguishable — the first two differ in hue and
#: in lightness, and no adjacent pair is a red/green confusion. A ninth member cycles rather than
#: reaching for a colour that only a wide-gamut display separates from the first eight.
CATEGORICAL_PALETTE: tuple[str, ...] = (
    "#2563eb",
    "#d97706",
    "#0891b2",
    "#7c3aed",
    "#16a34a",
    "#db2777",
    "#65a30d",
    "#9a3412",
)


def categorical_colors(members: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Each member paired with the colour it takes, in the declared order."""
    return tuple(
        (member, CATEGORICAL_PALETTE[index % len(CATEGORICAL_PALETTE)])
        for index, member in enumerate(members)
    )


COLOR_CAPABILITIES: frozenset[str] = frozenset({"node_color", "edge_color", "cluster_grouping", "cell_emphasis"})
"""Capabilities whose value resolves to a solid color (or a color gradient in scale mode)."""

TOKEN_CAPABILITIES: frozenset[str] = frozenset({"node_shape", "node_icon", "edge_emphasis"})
"""Capabilities whose value selects one of a fixed notation set keyed on the semantic tokens."""

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



def token_color(token: str) -> str:
    """The colour a style value paints as: a `#rrggbb` literal as-is, a token through the table.

    An unknown token answers neutral, which is what every adapter already did — a value outside its
    capability's domain is refused at save time, so reaching here means a definition predating that
    validation, and painting it grey is what such a definition already displayed.
    """
    if is_hex_color(token):
        return token
    return STYLE_TOKEN_COLORS.get(token, STYLE_TOKEN_COLORS["neutral"])


#: The colour an *unset* member takes: the value a schema declares as its `default`, which is what a
#: reader sees on an entity nobody has assessed. White rather than a point on the gradient, because
#: "not assessed" is not a low reading — placing it at the bottom of a red-to-green ramp would paint
#: an unknown as the worst case, and a reader cannot tell the two apart once it is coloured.
UNSET_MEMBER_COLOR = "#ffffff"

#: The gradients a reader can spread an ordered value set along, keyed by the name a request states.
#: Each is a run of **stops**, and the stops in the middle are the point of them.
#:
#: Interpolating red to green directly runs through brown, because the two channels cross over at the
#: middle and the values a reader most needs to tell apart come out as mud. Going through amber is
#: what every traffic-light scale a reader has seen already does. A single amber stop is still not
#: enough: the segment from amber to green passes through olive, so the upper half reads as neither.
#: The lime stop is what keeps the top of the scale green.
#:
#: **No stop is a neutral.** White means "not assessed", and a grey or near-white stop in the middle
#: of a scale says the same thing in the same picture — a reader cannot then tell an unassessed
#: element from a middling one. That rules out the obvious colour-blind-safe schemes, which are
#: diverging and pivot on a neutral.
#:
#: `red-green` is the default because it carries the meaning most of these value sets have, a ladder
#: from bad to good, with no legend needed. It is also the one pair a red/green colour-blind reader
#: cannot separate, which is why the second is not an afterthought. `yellow-blue` is that second one:
#: yellow and blue are the poles every common form of colour blindness preserves, it runs light to
#: dark so it survives greyscale, and it reaches neither grey nor white on the way.
ATTRIBUTE_GRADIENTS: dict[str, tuple[str, ...]] = {
    "red-green": ("#dc2626", "#fb923c", "#fde047", "#a3e635", "#22c55e"),
    "yellow-blue": ("#facc15", "#4ade80", "#06b6d4", "#2563eb", "#1e3a8a"),
}

DEFAULT_ATTRIBUTE_GRADIENT = "red-green"


def graded_colors(
    members: Sequence[str], *, unset: str | None = None, gradient: str = DEFAULT_ATTRIBUTE_GRADIENT
) -> tuple[tuple[str, str], ...]:
    """Each member paired with its colour: *unset* white, the rest spread along *gradient*.

    In **declared** order, which for a value set that means something — a maturity ladder, a risk
    band — is the order a reader expects to see. The unset member is taken out of the spread rather
    than given an end of it, so the remaining members still use the gradient's full range: with six
    members of which one is unset, five are spread, not five squeezed into four fifths of the ramp.

    A single graded member takes the gradient's far end. There is no position to interpolate to, and
    the far end is the one a reader reads as "arrived".
    """
    stops = ATTRIBUTE_GRADIENTS.get(gradient, ATTRIBUTE_GRADIENTS[DEFAULT_ATTRIBUTE_GRADIENT])
    graded = [member for member in members if member != unset]
    last = len(graded) - 1
    positions = {
        member: (1.0 if last <= 0 else index / last) for index, member in enumerate(graded)
    }
    return tuple(
        (
            member,
            UNSET_MEMBER_COLOR if member == unset else color_along_stops(stops, positions[member]),
        )
        for member in members
    )


def color_along_stops(stops: Sequence[str], position: float) -> str:
    """The colour at *position* through a run of stops, interpolating within the segment it falls in.

    The one place a scale becomes a colour. `scale_tokens` has always been a variable-length tuple
    and the served contract a list, so a gradient with a middle stop was representable before this —
    the adapter simply read the first two and interpolated between them, which is what ran a
    red-to-green scale through brown.
    """
    if len(stops) == 1:
        return interpolate_style_colors(stops[0], stops[0], 0.0)
    segments = len(stops) - 1
    scaled = max(0.0, min(1.0, position)) * segments
    index = min(int(scaled), segments - 1)
    return interpolate_style_colors(stops[index], stops[index + 1], scaled - index)


def interpolate_style_colors(near: str, far: str, position: float) -> str:
    """A point on a two-endpoint ramp, resolving each endpoint through the token table first.

    The arithmetic is `mix_colors` — the one lerp — so this adds exactly what is specific to a style
    value: that an endpoint may be a *token* rather than a literal, which only this module can resolve.

    Lower-cased, because a style value's colour is lower-case wherever this module states one and a
    function that answered `#DC2626` at one end of a ramp and `#dc2626` at the other would make every
    caller comparing two of them wrong. `mix_colors` returns upper case for the ontology's declared
    colours, which are written that way; the case is not part of the convention.
    """
    return mix_colors(token_color(near), token_color(far), position).lower()
