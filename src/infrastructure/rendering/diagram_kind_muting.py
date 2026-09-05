"""Quietening the element-kind colouring so an attribute reading is the loud one.

A diagram carries two colourings at once: an element is filled by its kind, and reading an attribute
repaints the elements carrying a value for it. `keep` leaves both loud and a reader cannot tell which
green they are looking at; `drop` answers that by discarding the kind, which is a fact they navigate
by. This is the third answer — keep the kind and turn it down.

**It works through the stereotype, not through the element, and that is what makes the legend right.**
Appending a second declaration for a stereotype replaces its fill, measured: PlantUML takes the last
declaration for a stereotype and an element's own colour suffix beats both, wherever in the body
either appears. So an element carrying an attribute value keeps the per-element colour the lens gave
it, an element carrying none takes its kind's muted fill, and *no* element line gains an override it
did not already have. The legend reads the body to decide which kinds are still on screen and asks
`overrides_colour` of each line — so muting this way leaves every muted kind named, where painting
each element individually would have silently emptied that section of the legend.

The composition is a second pass over the body, like the legend's, for the same reason: it appends
rather than weaving, so nothing here needs to know how an element line is spelled.
"""

from __future__ import annotations

from src.application.viewpoints.diagram_reading_lens import ElementKindColouring, ReadingLens
from src.domain.viewpoints.viewpoint_style_values import muted_element_kind_fill
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.archimate_legend import notations_referenced_in

_END = "@enduml"


def body_with_muted_element_kinds(
    body: str, *, lens: ReadingLens, declarations: ArchimateDeclarations
) -> str:
    """*body* with every stereotype it draws re-declared in its muted fill, or unchanged.

    Unchanged unless a reader asked for muting *and* gave an attribute to read: turning the kinds
    down with nothing turned up leaves a diagram that is merely faint, which is not what anyone meant
    by asking for a clearer one.
    """
    if lens.element_kind_colouring is not ElementKindColouring.MUTED or not lens.colour_by:
        return body
    muted = _muted_declarations(body, declarations)
    return _appended(body, muted) if muted else body


def _muted_declarations(body: str, declarations: ArchimateDeclarations) -> str:
    """A `skinparam` per stereotype the body draws, in its muted fill.

    Only the fill. The border, corner and glyph say what kind of thing an element is as much as the
    colour does, and muting those would be dropping the kind by another route.
    """
    return "\n".join(
        f"skinparam rectangle<<{name}>> {{\n  BackgroundColor {muted_element_kind_fill(notation.fill)}\n}}"
        for name, notation in sorted(notations_referenced_in(body, declarations).items())
        if notation.fill
    )


def _appended(body: str, block: str) -> str:
    """`block` placed before the body's terminator, or at the end where it has none.

    Before `@enduml` because PlantUML stops reading there; the position among the *elements* does not
    matter, which is measured and is why this need not find the preamble.
    """
    index = body.rfind(_END)
    if index < 0:
        return body.rstrip("\n") + "\n" + block + "\n"
    return body[:index] + block + "\n" + body[index:]
