"""Every style token is painted as something, and one table says what.

A token is opaque to domain code and resolved only by a surface adapter. That was one adapter for as
long as every renderer of a token was a browser; an ad-hoc reading lens renders diagrams server-side,
so the diagram renderer is an adapter too — and two palettes that can disagree is precisely the
incident `DOMAIN_COLORS` records, where "three hardcoded palettes disagreed on every domain".

So the palette is declared once, beside the token names it paints, and generated into the frontend's
constants. This gate is the other half of that arrangement, and it is the same shape as the one
guarding the FTS column weights — which caught a missing weight on the first change after it was
written, twice in this release.

Two failures it is here to prevent, neither of which shows up as an error at runtime:

* **A token with no colour.** `tokenColor` falls back to neutral grey, so a new token ships and paints
  every element the same colourless grey — a picture that renders cleanly and says nothing.
* **A colour with no token.** Dead vocabulary that reads as available. Worse, an author picking it
  from a list would have their choice refused at save time by a validator that never heard of it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.domain.hex_colors import is_hex_color
from src.domain.viewpoints.viewpoint_style_values import (
    CATEGORICAL_PALETTE,
    STYLE_TOKEN_COLORS,
    STYLE_VALUE_TOKENS,
    interpolate_style_colors,
)

_GENERATED = Path(__file__).resolve().parents[2] / "tools" / "gui" / "src" / "domain" / "types.generated.ts"
_RECORD = re.compile(
    r"export const STYLE_TOKEN_COLORS: Record<string, string> = \{(?P<body>.*?)\n\}", re.DOTALL
)
_ARRAY = re.compile(r"export const CATEGORICAL_PALETTE = \[(?P<body>.*?)\n\] as const", re.DOTALL)

#: The specification of the ramp, as sample points. Asserted **on both sides**: the matching table is
#: in `tools/gui/src/ui/lib/__tests__/viewpointStyleTokens.test.ts`, which asserts the browser adapter
#: reproduces these same values.
#:
#: A conformance pair rather than one gate, because the two implementations are in two languages and
#: neither can call the other. What has to agree is the convention — component-wise linear
#: interpolation in sRGB, position clamped — and the way to hold two languages to a convention is to
#: write down what it produces and check both against it. The endpoints below are the pair the ad-hoc
#: reading lens uses, at the positions a reader actually sees: both ends, the midpoint, and past each
#: end where the clamp is the only thing keeping the colour on the ramp.
RAMP_SAMPLES: tuple[tuple[str, str, float, str], ...] = (
    ("heat-low", "heat-high", 0.0, "#fbbf24"),
    ("heat-low", "heat-high", 0.5, "#ec7325"),
    ("heat-low", "heat-high", 1.0, "#dc2626"),
    ("heat-low", "heat-high", -1.0, "#fbbf24"),
    ("heat-low", "heat-high", 2.0, "#dc2626"),
    ("heat-near", "heat-far", 0.25, "#3d768f"),
)


def _generated_palette() -> dict[str, str]:
    """The palette as the frontend received it, read from the committed generated file.

    Read rather than regenerated: the question is whether what was *committed* agrees, which is the
    same question `git diff --exit-code` asks after the generator runs, from the other side.
    """
    match = _RECORD.search(_GENERATED.read_text(encoding="utf-8"))
    assert match is not None, "the generated constants no longer declare STYLE_TOKEN_COLORS"
    return json.loads("{" + match.group("body").rstrip().rstrip(",") + "}")


def test_every_declared_token_is_painted() -> None:
    missing = sorted(STYLE_VALUE_TOKENS - set(STYLE_TOKEN_COLORS))

    assert missing == [], (
        f"these tokens have no colour, so every element they style falls back to neutral grey and "
        f"the picture renders cleanly while saying nothing: {missing}"
    )


def test_nothing_is_painted_that_is_not_a_token() -> None:
    extra = sorted(set(STYLE_TOKEN_COLORS) - STYLE_VALUE_TOKENS)

    assert extra == [], (
        f"these colours name no declared token, so they are dead vocabulary that reads as available — "
        f"and an author choosing one would be refused at save time by a validator that never heard of "
        f"it: {extra}"
    )


def test_every_colour_is_a_hex_literal() -> None:
    """The adapters interpolate between these, so a named CSS colour or a gradient would break the
    ramp rather than the swatch — and it would break it only for `mode: "scale"`, on the one code path
    a reader reaches by asking a question about magnitude."""
    malformed = sorted(token for token, colour in STYLE_TOKEN_COLORS.items() if not is_hex_color(colour))

    assert malformed == [], f"not `#rrggbb`, so interpolation cannot read them: {malformed}"


def test_the_frontend_received_exactly_this_palette() -> None:
    """The generated half. Without this the server could resolve a token one way and the browser
    another, which is the arrangement this table exists to end."""
    assert _generated_palette() == STYLE_TOKEN_COLORS, (
        "the committed generated constants disagree with the declaration; run "
        "`uv run tools/ontology/generate_types.py` and commit the result"
    )


def _generated_palette_array() -> list[str]:
    match = _ARRAY.search(_GENERATED.read_text(encoding="utf-8"))
    assert match is not None, "the generated constants no longer declare CATEGORICAL_PALETTE"
    return json.loads("[" + match.group("body").rstrip().rstrip(",") + "]")


class TestTheCategoricalPalette:
    """The other colouring. Its own tests because its contract is different: a *sequence* whose
    position is the assignment, where the token table is a lookup whose order means nothing."""

    def test_every_colour_is_a_hex_literal(self) -> None:
        malformed = [colour for colour in CATEGORICAL_PALETTE if not is_hex_color(colour)]

        assert malformed == [], f"not `#rrggbb`: {malformed}"

    def test_no_colour_appears_twice(self) -> None:
        """Two members painted the same colour is a picture a reader cannot decode, and it would fail
        silently — the diagram renders, the legend lists both, and they look identical."""
        assert len(set(CATEGORICAL_PALETTE)) == len(CATEGORICAL_PALETTE)

    def test_the_frontend_received_the_palette_in_the_same_order(self) -> None:
        """In order, because the position *is* the assignment. A record would have passed a comparison
        of contents while the browser painted a different member each colour — which is the failure the
        endpoint ordering already produced once in this release, from exactly that mistake."""
        assert _generated_palette_array() == list(CATEGORICAL_PALETTE)


class TestTheRampConvention:
    """Half of a cross-language pair; the other half is the browser adapter's own test."""

    def test_the_sample_points_are_what_the_ramp_produces(self) -> None:
        produced = [
            (near, far, position, interpolate_style_colors(near, far, position))
            for near, far, position, _expected in RAMP_SAMPLES
        ]

        assert produced == list(RAMP_SAMPLES), (
            "the ramp no longer produces its recorded sample points. If the change is deliberate, "
            "update this table *and* the matching one in "
            "`tools/gui/src/ui/lib/__tests__/viewpointStyleTokens.test.ts` — a ramp read one way on a "
            "diagram and another in a table shows one rule as two colours"
        )

    def test_a_position_outside_the_range_saturates_rather_than_wrapping(self) -> None:
        assert interpolate_style_colors("heat-low", "heat-high", -5.0) == STYLE_TOKEN_COLORS["heat-low"]
