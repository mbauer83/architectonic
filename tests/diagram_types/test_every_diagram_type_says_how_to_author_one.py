"""Every registered diagram type states its authoring protocol, and bounds its label width.

Both gaps were found by authoring a diagram and looking at the output, and both were general
rather than specific to the type that exposed them.

`DiagramTypeWriteGuidance` has carried a `puml_notes` field throughout, and **only ArchiMate ever
populated it**. Every other type answered "how do I author one of these" with the *schema* of
`diagram_entities` — which says what is legal, not which connections are mandatory, which way a
relation reads, or what an omission silently does. That had to be reverse-engineered from an
existing file, i.e. after authoring one. The product's premise is that agents author model content;
a type whose wiring cannot be discovered will either go unused or be used wrongly, and the failure
is silent, because the diagram renders — just wrongly.

The width bound is the same shape of omission: a PlantUML box is as wide as its widest unwrapped
label, and four renderers emitted nothing to bound it. One sentence-long label stretched the page.

Neither is enforced by anything the type author has to remember, so it is enforced here. A new
diagram type fails this suite until it says how to author one.
"""

from __future__ import annotations

import re

import pytest

from src.infrastructure.diagram_type_registry import all_diagram_types, get_diagram_type

#: Types that render no PlantUML at all — a matrix is a markdown table, and the two assurance grids
#: are projected from the confidential store to a frontend grid. They still owe an author notes
#: (that is where "there is no PUML body, author it with …" has to be said), but no skinparam.
_NO_PUML_BODY = frozenset({"matrix", "uca-matrix", "fmea-matrix"})

#: GSN draws its own SVG rather than going through PlantUML; its label bound is a wrap column in
#: `gsn.svg_renderer`, asserted in `tests/assurance/test_gsn_diagram.py` rather than as a skinparam.
_NATIVE_SVG = frozenset({"gsn"})

#: Empty, and shrink-only. It held the seven `archimate-*` types while **B8** was deferred — the
#: measurement that closed it is recorded on `generic_puml_renderer.render_body`, where the bound is
#: now emitted like every other type's. Nothing may be added here: a type that cannot bound its
#: labels is a type whose widest label sets the width of the picture.
_WIDTH_BOUND_DEFERRED: frozenset[str] = frozenset()


def _type_names() -> list[str]:
    return sorted(all_diagram_types())


def test_the_scan_sees_the_registry_it_means_to() -> None:
    # Without this, a registry that returned nothing would report every type compliant.
    names = _type_names()
    assert len(names) > 8, names
    assert {"activity", "sequence", "matrix"} <= set(names), names


def test_the_deferred_set_names_types_that_exist() -> None:
    """A deferral that has outlived its subject stops being a deferral and becomes a lie.

    B8 exempts the ArchiMate types from the width bound. If one is renamed or retired the exemption
    would silently widen to nothing, or keep excusing a name nobody serves."""
    registered = set(_type_names())
    stale = sorted((_NO_PUML_BODY | _NATIVE_SVG | _WIDTH_BOUND_DEFERRED) - registered)
    assert stale == [], f"these exemptions name diagram types that are not registered: {stale}"


@pytest.mark.parametrize("diagram_type", _type_names())
def test_the_type_says_how_to_author_one(diagram_type: str) -> None:
    notes = get_diagram_type(diagram_type).write_guidance().puml_notes

    assert notes, (
        f"{diagram_type!r} returns no puml_notes: an author is left to infer the wiring protocol "
        "from an existing file. Say which connection types wire what to what, which are mandatory, "
        "and what an omission does."
    )
    # A note that names nothing concrete is decoration. Every type's protocol is expressed through
    # named keys, named connection types or a worked example — so at least one note quotes an
    # identifier from the payload it describes.
    joined = "\n".join(notes)
    assert re.search(r"[a-z]+[-_][a-z]+", joined), (
        f"{diagram_type!r}'s notes name no payload key or connection type: {joined[:200]!r}"
    )


@pytest.mark.parametrize(
    "diagram_type",
    [
        name for name in _type_names()
        if name not in _NO_PUML_BODY | _NATIVE_SVG | _WIDTH_BOUND_DEFERRED
    ],
)
def test_the_type_bounds_how_wide_a_label_may_make_it(diagram_type: str) -> None:
    """Asserted on the emitted body, not on the config: a type may declare a width and forget
    to emit it, which is the state four of these were in."""
    module = get_diagram_type(diagram_type)
    header = "\n".join(_puml_header_lines(module))

    assert re.search(r"^skinparam wrapWidth \d+$", header, flags=re.M), (
        f"{diagram_type!r} emits no wrapWidth: one sentence-long label sets the width of the whole "
        f"picture. Use `label_wrap_skinparams`. Header was: {header[:300]!r}"
    )


def _puml_header_lines(module: object) -> list[str]:
    """The skinparams a type puts at the top of its body, however it assembles one.

    Read from the type's own renderer against an empty payload — every renderer here emits its
    header before it has anything to draw, which is exactly what makes the header assertable
    without knowing any type's `diagram_entities` shape.
    """
    from pathlib import Path

    renderer = module.renderer  # type: ignore[attr-defined]
    try:
        body = renderer.render_body(
            "Header Probe", [], [], str(module.name), Path("/nonexistent"),  # type: ignore[attr-defined]
            diagram_entities={}, diagram_connections=[],
        )
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"renderer refused an empty payload, so its header cannot be read: {exc}")
    return body.splitlines()
