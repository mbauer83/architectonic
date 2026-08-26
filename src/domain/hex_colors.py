"""What a `#rrggbb` colour is, and the arithmetic over one.

A home for this because the arithmetic was being written a second time. `element_appearance` already
mixed two colours — that is how a de-emphasised fill and a derived border are computed — and a
server-side heat map needs the identical operation under the name "interpolate between two scale
endpoints". Two lerps over the same three bytes is the shape of duplication this repository keeps
paying for, so there is one, here, and the callers name it for what they are doing.

Vocabulary-free on purpose. Nothing here knows about a style token, an ArchiMate domain, a diagram
type or a scale: those are the callers' concerns, and a generic component that named one of them would
be the boundary violation the standards document is most explicit about. What it knows is bytes.

**Tolerant, not strict.** A value that is not a six-digit hex colour is returned unchanged rather than
raising, because every caller receives colours from declared content — an ontology's YAML, an author's
style value — and the existing behaviour a definition already displayed is the right answer for one
that predates validation.
"""

from __future__ import annotations

import re

_HEX_COLOR = re.compile(r"^#?[0-9a-fA-F]{6}$")


def is_hex_color(value: str) -> bool:
    """True for an explicit ``#rrggbb`` colour literal."""
    return value.startswith("#") and _HEX_COLOR.match(value) is not None


def hex_channels(color: str) -> tuple[int, int, int] | None:
    """*color*'s three bytes, or None if it is not a six-digit hex colour."""
    value = color.lstrip("#")
    if len(value) != 6:
        return None
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return None


def mix_colors(color: str, toward: str, amount: float) -> str:
    """*color* moved *amount* of the way to *toward*. Either colour unreadable leaves it alone.

    **Component-wise linear interpolation in sRGB, `amount` clamped to [0, 1].** The convention is
    stated because it is the thing that has to agree rather than the arithmetic: `viewpointStyleTokens.ts`
    interpolates the same two scale endpoints for a table badge that this computes for a diagram
    element, and a rule that reads as one colour on the picture and another in the table is one rule
    shown as two. Interpolating in linear-light RGB or a perceptual space would give a *better* gradient
    and a *different* one, so the choice is recorded here and
    `tests/architecture/test_every_style_token_has_a_colour.py` holds both sides to a sample table.

    **A half-way channel rounds up**, and that is not a detail. `round` in Python is half-to-*even*
    and `Math.round` in JavaScript is half-*up*, so the two sides of the pair disagreed by one on
    exactly the midpoint of the default ramp — the position a reader sees most — and agreed everywhere
    else. The conformance table caught it on the first run. Half-up is chosen because it is what the
    browser adapter, CSS and canvas arithmetic all already do; the channels are byte values and never
    negative, so `int(x + 0.5)` is the whole rule.

    Uppercase output, which is what the shipped mixing already returned and what the ontology's own
    declared colours look like. PlantUML and CSS are both case-insensitive about a hex colour, so the
    case is not part of the convention — the numbers are.
    """
    left, right = hex_channels(color), hex_channels(toward)
    if left is None or right is None:
        return color
    ratio = min(max(amount, 0.0), 1.0)
    mixed = (int(a + (b - a) * ratio + 0.5) for a, b in zip(left, right, strict=True))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def relative_luminance(color: str) -> float | None:
    """*color*'s WCAG relative luminance, or None if it is not a hex colour.

    WCAG 2.1's definition, sRGB linearisation included — the same quantity a contrast checker computes,
    rather than a guess at brightness from the raw bytes.
    """
    channels = hex_channels(color)
    if channels is None:
        return None

    def linear(byte: int) -> float:
        value = byte / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(component) for component in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


#: Text on a light fill and text on a dark one. Near-black rather than black and near-white rather
#: than white, because both sit on coloured fills where the full extremes read as holes.
INK_ON_LIGHT = "#252327"
INK_ON_DARK = "#f5f5f5"

#: The relative luminance above which a fill counts as light. Halfway, on the WCAG scale.
_LIGHT_ABOVE = 0.5


def readable_ink(fill: str) -> str:
    """Which ink to write on *fill*.

    A renderer that writes one fixed ink over a ramp writes it over both ends. The first heat map this
    repository drew put `#555` on `#dc2626`; the picture rendered cleanly, passed every gate, and could
    not be read — which is why the ink is computed from the fill rather than chosen once. An
    unreadable fill answers dark ink, which is what a light background wants and what every surface
    here defaults to.
    """
    luminance = relative_luminance(fill)
    return INK_ON_LIGHT if luminance is None or luminance > _LIGHT_ABOVE else INK_ON_DARK
