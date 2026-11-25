"""The palette draws five types a rendered diagram does not mark, and the diagram stays as it was.

The glyph table serves two readers: the GUI's palette and lists, and the ontology's sprites, which a
rendered ArchiMate element carries as its type mark. Junctions, collaborations, groupings and locations
gained glyphs for the palette only; a sprite for them would change every existing picture that
draws one, so the ontology must still offer none.
"""

from __future__ import annotations

import json

from src.ontologies.archimate_4._loader import _GLYPHS_PATH, _PACKAGE_DIR, load_archimate_4_module

_UNMARKED = ("and-junction", "or-junction", "collaboration", "grouping", "location")


def test_the_palette_has_a_glyph_for_each_unmarked_type() -> None:
    table = json.loads(_GLYPHS_PATH.read_text(encoding="utf-8"))
    assert {t: table["unmarked_types"].get(t) in table["kinds"] for t in _UNMARKED} == dict.fromkeys(_UNMARKED, True)


def test_a_rendered_diagram_marks_none_of_them() -> None:
    module = load_archimate_4_module(_PACKAGE_DIR, svg_converter=lambda markup: markup)
    assert {t: module.sprite_for(t) for t in _UNMARKED} == dict.fromkeys(_UNMARKED)
    assert module.sprite_for("business-actor") is not None
