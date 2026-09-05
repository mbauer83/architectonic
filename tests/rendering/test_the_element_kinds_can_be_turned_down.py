"""Muting the element-kind colouring, and the ordering that makes it work at all.

A reader colouring by an attribute sees two colourings at once. `keep` leaves both loud, `drop`
discards the kind, and `dim` turns it down — the kinds stay told apart and stay named in the legend,
while the attribute is unmistakably the reading.

**The ordering is the load-bearing part and it is not obvious.** Muting speaks in stereotype
declarations, and preparing a body for render *restates every stereotype declaration from the
ontology* — that is the rule keeping one owner for what a kind looks like. A muted declaration
written before preparation therefore survives as a block and comes back in the authored colour, which
was measured rather than guessed. So muting is applied after preparation, and the test that pins that
is the one below about a prepared body: without it, the feature fails silently and looks like
`keep`.
"""

from __future__ import annotations

from src.application.viewpoints.diagram_reading_lens import ElementKindColouring, ReadingLens
from src.domain.viewpoints.viewpoint_style_values import PAGE_GROUND, muted_element_kind_fill
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations
from src.infrastructure.rendering.diagram_kind_muting import body_with_muted_element_kinds

_BODY = """@startuml x
skinparam rectangle<<function>> {
  BackgroundColor #E5DFD3
}
rectangle "A Function" <<function>> as FN_a
@enduml
"""


def _declarations() -> ArchimateDeclarations:
    """The fill is read back out of the block, as it is in production — not stated twice."""
    return ArchimateDeclarations(
        header="",
        stereotype_blocks={
            "function": (
                "skinparam rectangle<<function>> {\n"
                "  BackgroundColor #E5DFD3\n"
                "  BorderColor #45433F\n"
                "  RoundCorner 14\n"
                "}"
            )
        },
        sprites={},
        relation_macros={},
    )


def _muting_lens() -> ReadingLens:
    return ReadingLens(colour_by="maturity", element_kind_colouring=ElementKindColouring.MUTED)


# ── what muting does to a colour ─────────────────────────────────────────────


def test_a_muted_fill_lies_between_the_authored_one_and_the_page() -> None:
    muted = muted_element_kind_fill("#E5DFD3")
    assert muted not in {"#E5DFD3", PAGE_GROUND}


def test_muting_is_idempotent_in_direction_not_in_value() -> None:
    """Muting twice goes further toward the page, so nothing may mute an already-muted fill."""
    once = muted_element_kind_fill("#E5DFD3")
    assert muted_element_kind_fill(once) != once


def test_a_fill_without_its_hash_is_accepted() -> None:
    """A declaration's fill is read from PUML, where the `#` is part of the syntax, not the value."""
    assert muted_element_kind_fill("E5DFD3") == muted_element_kind_fill("#E5DFD3")


# ── when it applies ──────────────────────────────────────────────────────────


def test_a_reader_who_asked_for_muting_gets_a_muted_declaration() -> None:
    out = body_with_muted_element_kinds(_BODY, lens=_muting_lens(), declarations=_declarations())
    assert muted_element_kind_fill("#E5DFD3") in out


def test_keeping_the_kind_colouring_changes_nothing() -> None:
    lens = ReadingLens(colour_by="maturity", element_kind_colouring=ElementKindColouring.KEPT)
    assert body_with_muted_element_kinds(_BODY, lens=lens, declarations=_declarations()) == _BODY


def test_dropping_the_kind_colouring_changes_nothing_here() -> None:
    """`drop` is the lens's own business — it paints elements, not declarations."""
    lens = ReadingLens(colour_by="maturity", element_kind_colouring=ElementKindColouring.DROPPED)
    assert body_with_muted_element_kinds(_BODY, lens=lens, declarations=_declarations()) == _BODY


def test_muting_with_nothing_to_read_changes_nothing() -> None:
    """Turning the kinds down with no attribute turned up is a faint diagram, not a clearer one."""
    lens = ReadingLens(colour_by="", element_kind_colouring=ElementKindColouring.MUTED)
    assert body_with_muted_element_kinds(_BODY, lens=lens, declarations=_declarations()) == _BODY


def test_a_stereotype_the_body_does_not_draw_is_not_declared() -> None:
    body = "@startuml x\nrectangle \"Plain\" as P\n@enduml\n"
    assert body_with_muted_element_kinds(body, lens=_muting_lens(), declarations=_declarations()) == body


# ── how it is written ────────────────────────────────────────────────────────


def test_only_the_fill_is_muted() -> None:
    """Border, corner and glyph say what kind of thing an element is; muting those would drop it.

    The declarations carry a border and a corner and the body carries neither, so anything of either
    in the result came from the block this appended.
    """
    out = body_with_muted_element_kinds(_BODY, lens=_muting_lens(), declarations=_declarations())
    assert muted_element_kind_fill("#E5DFD3") in out
    assert "BorderColor" not in out
    assert "RoundCorner" not in out


def test_the_declaration_lands_before_the_terminator() -> None:
    """PlantUML stops reading at `@enduml`, so anything after it is not a declaration at all."""
    out = body_with_muted_element_kinds(_BODY, lens=_muting_lens(), declarations=_declarations())
    assert out.rstrip().endswith("@enduml")
    assert out.index(muted_element_kind_fill("#E5DFD3")) < out.rindex("@enduml")


def test_a_body_with_no_terminator_still_gets_the_declaration() -> None:
    body = "@startuml x\nrectangle \"A Function\" <<function>> as FN_a\n"
    out = body_with_muted_element_kinds(body, lens=_muting_lens(), declarations=_declarations())
    assert muted_element_kind_fill("#E5DFD3") in out


# ── the ordering the whole feature rests on ──────────────────────────────────


def test_muting_survives_only_after_the_declarations_have_been_restated() -> None:
    """The measured fact this design exists for.

    Preparing a body restates every stereotype declaration from the ontology, so a muted declaration
    written *before* preparation is rewritten back to the authored colour. Applying muting after
    preparation is what makes it stick, and this states both halves so the order cannot be quietly
    reversed.
    """
    declarations = _declarations()
    before = body_with_muted_element_kinds(_BODY, lens=_muting_lens(), declarations=declarations)
    restated = declarations.restated_in(before)
    assert muted_element_kind_fill("#E5DFD3") not in restated, (
        "restating the declarations should overwrite a muted one written before it"
    )

    after = body_with_muted_element_kinds(restated, lens=_muting_lens(), declarations=declarations)
    assert muted_element_kind_fill("#E5DFD3") in after
