"""The level of measurement an attribute schema declares, and what it licenses.

JSON Schema types a value's syntax, not what may be done with it: a severity and an owner are
both strings, yet only one of them has a rank. ``x-scale`` records the level of measurement,
following the ``x-`` convention this repository already uses for schema keywords of its own
(``x-recommended``).

``ordinal`` means the attribute's declared ``enum`` is written in ascending rank order, so its
members compare and ``min``/``max`` pick one of them. What follows from that is as important as
what it permits:

* Rank is a position in one particular enum, so two ordinals drawn from different enums are not
  commensurable and must not be compared. Their ranks are numbers about different things.
* Summing or averaging ordinals is a category error, not a rounding concern: the distance
  between adjacent members is unknown and not uniform, so a mean of ``{minor, catastrophic}``
  denotes nothing. This is the same reason a risk priority number computed by multiplying
  ordinals is not a quantity.
* A value outside the enum has no rank at all. It never resolves to the first position, because
  a rank of zero reads as the *lowest* member and would flatter unrecognised data into looking
  benign.

Declaring the level rather than special-casing attribute names is what keeps this honest: no
code decides that a particular attribute happens to be ordered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: The schema keyword carrying an attribute's level of measurement.
SCALE_KEYWORD = "x-scale"

#: The one level of measurement this repository declares. Nominal is the absence of a
#: declaration, and no interval or ratio attribute has needed distinguishing from a plain
#: number, so neither is invented here.
ORDINAL_SCALE = "ordinal"

#: The scalar kind an ordinal-declared attribute resolves to in the query type system. It is a
#: kind of its own rather than a flavour of string, so that comparing, reducing and aggregating
#: it can be decided by type rather than by inspecting each value.
ORDINAL_KIND = "ordinal"


def declared_scale(prop: Mapping[str, object] | None) -> str | None:
    """The level of measurement an attribute-schema property declares, if any."""
    if not isinstance(prop, Mapping):
        return None
    declared = prop.get(SCALE_KEYWORD)
    return str(declared) if isinstance(declared, str) and declared else None


def declares_ordinal(prop: Mapping[str, object] | None) -> bool:
    """Whether this property declares its enum to be in ascending rank order."""
    return declared_scale(prop) == ORDINAL_SCALE


def ordinal_rank(value: object, scale: Sequence[str]) -> int | None:
    """The position of ``value`` in ``scale``, or None when it has no position there.

    None rather than a fallback: an unrecognised value is unranked, and any numeric stand-in
    would place it somewhere on the scale it does not belong.
    """
    if not isinstance(value, str):
        return None
    try:
        return tuple(scale).index(value)
    except ValueError:
        return None


def ordinal_extreme(values: Sequence[object], *, highest: bool, scale: Sequence[str]) -> object:
    """The highest- or lowest-ranked member among ``values``, by declared rank not by spelling.

    Returns the member itself, never its rank: a position is how the choice was made, not the
    value chosen. Unranked values take no part, and if nothing ranks the answer is absent rather
    than an arbitrary pick.
    """
    ranked = [(rank, item) for item in values for rank in (ordinal_rank(item, scale),) if rank is not None]
    if not ranked:
        return None
    chosen = max(ranked, key=lambda pair: pair[0]) if highest else min(ranked, key=lambda pair: pair[0])
    return chosen[1]


def ordinal_scales_match(left: Sequence[str] | None, right: Sequence[str] | None) -> bool:
    """Whether two ordinal attributes are drawn from the same enum, and so are comparable.

    Identity of the member sequence, not of length or membership: two scales sharing members in
    a different order rank them differently, which is exactly the confusion to refuse.
    """
    if left is None or right is None:
        return False
    return tuple(left) == tuple(right)
