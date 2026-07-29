"""WU-V2: the guillemet formatter renders a concept's specialization set as one
comma-separated stereotype (ArchiMate §15.2)."""

from __future__ import annotations

from src.infrastructure.rendering.archimate_relation_rendering import format_specializations_guillemet


def test_single_name_matches_the_bare_form() -> None:
    assert format_specializations_guillemet(["Business Service"]) == "«Business Service»"


def test_several_names_are_comma_separated_in_order() -> None:
    assert format_specializations_guillemet(["Business Service", "Audited"]) == "«Business Service, Audited»"


def test_blanks_are_dropped() -> None:
    assert format_specializations_guillemet(["", "Audited", ""]) == "«Audited»"


def test_an_empty_set_renders_nothing() -> None:
    assert format_specializations_guillemet([]) == ""
    assert format_specializations_guillemet(["", ""]) == ""
