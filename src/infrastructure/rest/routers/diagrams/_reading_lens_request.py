"""How an ad-hoc reading arrives over HTTP, and what is refused on the way in.

Its own module because it is the trust boundary, not because `_serving.py` grew. A reader's colour
travels as text in a query string and ends up inside a PUML declaration, whose compound colour form is
`#back:…;line:…;text:…` — `;`-separated. A value carrying a `;` would therefore not be a bad colour; it
would be extra PUML in a body assembled from a URL. So the parsing and the refusal are one thing, in
one place, with the tests that hold it.

**Tolerant about shape, strict about colour.** A malformed pair, a missing half of a gradient or a
colour that is not six hex digits is *dropped*, and the element keeps the colour its declaration gives
it. A 400 would be the wrong answer: a stale or hand-edited URL should still draw the diagram, and a
reader whose gradient did not take can see that from the picture. What is never tolerated is a colour
reaching the renderer unrecognised.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.hex_colors import is_hex_color
from src.domain.viewpoints.viewpoint_style_values import (
    ATTRIBUTE_GRADIENTS,
)


def _colour(value: str) -> str | None:
    """*value* as a `#rrggbb` colour, or None if it is not one.

    **The refusal is the point.** A reader's colour is written into a PUML declaration as
    `#back:…;line:…;text:…`, so a value carrying a `;` would not be a bad colour — it would be extra
    PUML in a body assembled from a query string. Only six hex digits are accepted, with or without the
    leading `#`, and anything else is dropped in favour of the declared colour. Dropped rather than
    refused with a 400: a stale or hand-edited URL should still draw the diagram.
    """
    candidate = value.strip()
    candidate = candidate if candidate.startswith("#") else f"#{candidate}"
    return candidate.lower() if is_hex_color(candidate) else None


def _ramp(value: str) -> tuple[str, str] | None:
    """A reader's gradient, given as `near:far`. Both ends must be colours or neither is used."""
    if ";" in value:
        return None
    near, _, far = value.partition(":")
    resolved = (_colour(near), _colour(far))
    return None if None in resolved else (resolved[0] or "", resolved[1] or "")


def _key(pairs: Sequence[str]) -> dict[str, str]:
    """A reader's per-member colours, each given as `member:colour`.

    Split at the **last** colon, because a member is a value from the model and may contain one while a
    hex colour never does. A pair whose tail is not a colour is dropped and the member keeps its
    declared colour, which is the same tolerance `_colour` applies for the same reason.

    **A pair containing a semicolon is refused whole**, before the split. Splitting at the last colon
    alone was not enough: `active:dc2626;line:000000` splits into the member `active:dc2626;line` and
    the perfectly valid colour `000000`, so the semicolon passed the colour check by being on the other
    side of it. Nothing unsafe reached the renderer — a member is only ever compared against attribute
    values, never written into a declaration — but a reader would have got a silent mapping for a member
    no entity has, which is a worse answer than no mapping. A semicolon in a value set member is
    conceivable and vanishingly rare; the ambiguity is not worth it.
    """
    key: dict[str, str] = {}
    for pair in pairs:
        if ";" in pair:
            continue
        member, separator, raw = pair.rpartition(":")
        colour = _colour(raw) if separator else None
        if member and colour is not None:
            key[member] = colour
    return key


def _gradient(value: str) -> str | None:
    """The named gradient a request asks for, or None where it names none this product has.

    None rather than the default name, because the two are different requests: a graded value set is
    coloured by the default either way, and a ramp keeps its magnitude pair until a reader names a
    gradient. An unknown name falls back to None rather than failing — a gradient is a reading
    preference carried in a URL, and a stale or mistyped one should still draw the diagram.
    """
    return value if value in ATTRIBUTE_GRADIENTS else None


def lens_from_query(
    colour_by: str, printed: Sequence[str], ramp: str, key: Sequence[str], legend: bool,
    gradient: str = "",
) -> ReadingLens:
    """The reader's request, normalised. Blank names are dropped and order is kept."""
    return ReadingLens(
        colour_by=colour_by.strip(),
        printed=tuple(dict.fromkeys(name.strip() for name in printed if name.strip())),
        ramp=_ramp(ramp) if ramp else None,
        key=_key(key),
        gradient=_gradient(gradient),
        legend=legend,
    )
