"""The names an element is known by on a diagram, most specific first — what icon statements are keyed by.

A model element's names are its applied specializations in order, then its type. Where a diagram draws
it as a type of the diagram's own — a C4 container drawn for an application component — that type
follows, so a statement in either vocabulary reaches it. Stated here once, because the renderers and
the editor's preview must classify an instance alike, or the editor shows an icon the picture does not.
"""

from __future__ import annotations

from collections.abc import Sequence


def names_most_specific_first(
    element_type: str, specializations: Sequence[str], drawn_as: str | None = None
) -> tuple[str, ...]:
    """Specializations, then the type, then the type the diagram draws the element as, where that differs."""
    names = (*[name for name in specializations if name], element_type)
    return (*names, drawn_as) if drawn_as and drawn_as not in names else names
