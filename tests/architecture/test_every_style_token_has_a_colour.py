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

from src.domain.viewpoints.viewpoint_style_values import (
    STYLE_TOKEN_COLORS,
    STYLE_VALUE_TOKENS,
    is_hex_color,
)

_GENERATED = Path(__file__).resolve().parents[2] / "tools" / "gui" / "src" / "domain" / "types.generated.ts"
_RECORD = re.compile(
    r"export const STYLE_TOKEN_COLORS: Record<string, string> = \{(?P<body>.*?)\n\}", re.DOTALL
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
