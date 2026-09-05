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
from typing import Annotated

from fastapi import Query

from src.application.viewpoints.diagram_reading_lens import ElementKindColouring, ReadingLens
from src.domain.hex_colors import is_hex_color
from src.domain.viewpoints.viewpoint_style_values import (
    ATTRIBUTE_GRADIENTS,
)

# ── How the reading is declared, once ────────────────────────────────────────
#
# Two operations take this lens — serving a diagram as SVG, and downloading one — because a lensed
# download renders through the *same* call the browser display uses, which is what stops an export
# becoming a second opinion about the display. Two operations taking one lens is one declaration,
# here beside the parsing, so a parameter cannot be added to the reader and missed by the export.
#
# **The descriptions say what each parameter is, not why a caller passes it.** The two spellings that
# differed said "the current display is coloured by" and "the current display prints", which describe
# the download's motive rather than the parameter; that belongs in the download operation's own
# description, where it already is, and a shared parameter cannot carry one caller's reason.

ColourBy = Annotated[str, Query(description="Attribute to colour the drawn elements by")]

Printed = Annotated[
    list[str], Query(alias="print", description="Attribute values to print with the elements")
]

Ramp = Annotated[
    str, Query(description="A gradient for a continuous attribute, as `near:far` in #rrggbb")
]

Key = Annotated[
    list[str], Query(description="A colour for one value, as `member:#rrggbb`; repeatable")
]

Legend = Annotated[
    bool, Query(description="Draw a legend explaining the notation this diagram uses")
]

Gradient = Annotated[
    str,
    Query(description="Which named gradient an ordered value set is spread along — "
                      "`red-green`, `yellow-blue` for a red/green colour-blind reader, or "
                      "either reversed (`green-red`, `blue-yellow`) for a scale whose high end "
                      "is the bad one. Absent leaves a graded set on the default and a ramp on "
                      "its magnitude pair"),
]

ElementKindColouringParameter = Annotated[
    str,
    Query(description="What becomes of the colour an element has for being what it is, while an "
                      "attribute is read — `keep` for both colourings at once, `dim` to turn the "
                      "kinds down so they are still told apart but the attribute is the loud "
                      "colouring, `drop` to give every element the attribute says nothing about "
                      "the same neutral the unset member takes. Acts only alongside `colour_by`"),
]


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


def _element_kind_colouring(value: str) -> ElementKindColouring:
    """The treatment a request asks for, or the one that changes nothing where it names none.

    Falling back rather than refusing, for the reason `_gradient` falls back: this travels in a URL,
    and a stale or mistyped name should still draw the diagram. Keeping is the safe fallback because
    it is what the diagram already does — a name nobody recognises must not silently repaint every
    element the reader did not ask about.
    """
    try:
        return ElementKindColouring(value.strip().lower())
    except ValueError:
        return ElementKindColouring.KEPT


def lens_from_query(
    colour_by: str, printed: Sequence[str], ramp: str, key: Sequence[str], legend: bool,
    gradient: str = "", element_kind_colouring: str = "",
) -> ReadingLens:
    """The reader's request, normalised. Blank names are dropped and order is kept."""
    return ReadingLens(
        colour_by=colour_by.strip(),
        printed=tuple(dict.fromkeys(name.strip() for name in printed if name.strip())),
        ramp=_ramp(ramp) if ramp else None,
        key=_key(key),
        gradient=_gradient(gradient),
        legend=legend,
        element_kind_colouring=_element_kind_colouring(element_kind_colouring),
    )
