"""An element shows the most specific icon stated for it that resolves and applies to it."""

from __future__ import annotations

import pytest

from src.application.icons.effective_icons import (
    EffectiveIcon,
    effective_icon,
    icon_assignments,
    names_most_specific_first,
)
from src.domain.icons.applicability import applicability_from
from src.domain.icons.icon_ref import IconRef, IconTarget, SharedIcon, icon_ref_from
from src.domain.icons.resolved_icon import ResolvedIcon

INSTANCE, TYPE, SPEC, DEFAULT, NARROW = (f"ICO@1.{k}" for k in ("inst1", "type1", "spec1", "dflt1", "narr1"))


def _icon(digest: str, *, applies_to: tuple[str, ...] = (), style: str = "badge") -> ResolvedIcon:
    return ResolvedIcon(b"png", digest, 128, 128, applicability_from(applies_to), style)  # type: ignore[arg-type]


LIBRARY = {
    INSTANCE: _icon("instance"),
    TYPE: _icon("type", style="figure"),
    SPEC: _icon("spec", applies_to=("kubernetes-cluster",)),
    DEFAULT: _icon("default"),
    NARROW: _icon("narrow", applies_to=("vm",)),
}


def _resolve(target: IconTarget) -> ResolvedIcon | None:
    return LIBRARY.get(target.icon_id) if isinstance(target, SharedIcon) else None


def _shown(
    statements: dict, *, specializations: tuple[str, ...] = ("kubernetes-cluster",), default: str | None = None
) -> EffectiveIcon | None:
    def specialization_default(name: str) -> IconRef | None:
        return icon_ref_from(default) if default and name == "kubernetes-cluster" else None

    return effective_icon(
        "NOD@1.node01",
        names_most_specific_first("technology-node", specializations),
        icon_assignments(statements),
        _resolve,
        specialization_default,
    )


ALL = {
    "display_icons": {"NOD@1.node01": INSTANCE},
    "type_icons": {"kubernetes-cluster": SPEC, "technology-node": TYPE},
}


@pytest.mark.parametrize(
    ("statements", "digest", "level"),
    [
        (ALL, "instance", "instance"),
        ({"type_icons": ALL["type_icons"]}, "spec", "type"),
        ({"type_icons": {"technology-node": TYPE}}, "type", "type"),
    ],
    ids=["instance-wins", "specialization-beats-type", "type"],
)
def test_the_most_specific_level_wins(statements: dict, digest: str, level: str) -> None:
    shown = _shown(statements)

    assert shown is not None and (shown.icon.render_digest, shown.level) == (digest, level)


def test_the_specialization_default_decides_when_the_diagram_states_nothing() -> None:
    shown = _shown({}, default=DEFAULT)

    assert shown is not None and (shown.icon.render_digest, shown.level) == ("default", "specialization-default")


def test_nothing_stated_keeps_the_type_glyph() -> None:
    assert _shown({}) is None


def test_an_icon_that_does_not_apply_is_passed_over_for_the_next_level() -> None:
    shown = _shown({"display_icons": {"NOD@1.node01": NARROW}, "type_icons": {"technology-node": TYPE}})

    assert shown is not None and shown.icon.render_digest == "type"


def test_an_icon_that_does_not_resolve_is_passed_over() -> None:
    shown = _shown({"display_icons": {"NOD@1.node01": "ICO@1.gone01"}, "type_icons": {"technology-node": TYPE}})

    assert shown is not None and shown.icon.render_digest == "type"


def test_a_specialization_icon_is_not_shown_on_the_type_without_it() -> None:
    assert _shown({"type_icons": {"kubernetes-cluster": SPEC}}, specializations=()) is None


def test_the_style_is_the_reference_s_or_else_the_icon_s_own() -> None:
    own = _shown({"type_icons": {"technology-node": TYPE}})
    stated = _shown({"type_icons": {"technology-node": {"icon": TYPE, "style": "badge"}}})

    assert own is not None and own.style == "figure"
    assert stated is not None and stated.style == "badge"


def test_a_malformed_entry_is_left_out_rather_than_failing_the_diagram() -> None:
    assignments = icon_assignments({"display_icons": {"A": "not-an-icon", "B": INSTANCE}, "type_icons": [1, 2]})

    assert list(assignments.by_instance) == ["B"] and not assignments.by_name
