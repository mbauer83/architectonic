"""An area narrows what goes in it, and narrowing warns.

The area's declaration used to scope one search box and nothing else. These hold the rule itself:
what the permitted set is read from, that a note outside it is warned about rather than refused, and
that the answer comes back in the shape a link's verdict already has.
"""

from __future__ import annotations

import pytest

from src.domain.scratchpad import Area, Note, NoteFinding, area_narrowing, note_verdict

_DOMAINS = {"goal": "motivation", "capability": "strategy", "application-component": "application"}


def _narrowing(note: Note, area: Area | None) -> NoteFinding | None:
    return area_narrowing(note, area, domain_of=_DOMAINS.get)


def _element(element_type: str) -> Note:
    return Note(id="n1", title="A", destination="element", element_type=element_type)


_STRATEGY = Area(id="strategy", label="Vision & strategy", permitted_domains=("motivation", "strategy"))


class TestWhatAnAreaPermits:
    def test_a_type_of_a_domain_the_area_holds_is_inside(self) -> None:
        assert _narrowing(_element("goal"), _STRATEGY) is None

    def test_a_type_of_another_domain_is_outside_and_named(self) -> None:
        finding = _narrowing(_element("application-component"), _STRATEGY)

        assert finding is not None
        assert "application-component is outside what it permits" in finding.message
        assert "Vision & strategy" in finding.message
        assert finding.narrowed_by == "strategy"

    def test_types_the_area_names_outright_win_over_its_domains(self) -> None:
        area = Area(id="a", label="A", permitted_domains=("motivation",),
                    permitted_element_types=("capability",))

        assert _narrowing(_element("capability"), area) is None
        assert _narrowing(_element("goal"), area) is not None

    def test_an_area_that_declares_nothing_permits_everything(self) -> None:
        assert _narrowing(_element("application-component"), Area(id="p", label="Portfolio")) is None

    def test_a_note_in_no_area_is_permitted_everything(self) -> None:
        assert _narrowing(_element("application-component"), None) is None

    def test_a_note_narrowed_only_to_a_domain_is_judged_on_the_domain(self) -> None:
        inside = Note(id="n1", title="A", destination="element", domain="strategy")
        outside = Note(id="n1", title="A", destination="element", domain="application")

        assert _narrowing(inside, _STRATEGY) is None
        assert "application is outside" in _narrowing(outside, _STRATEGY).message  # type: ignore[union-attr]

    def test_an_area_naming_only_types_says_nothing_about_a_bare_domain(self) -> None:
        area = Area(id="a", label="A", permitted_element_types=("capability",))

        assert _narrowing(Note(id="n1", title="A", destination="element", domain="application"), area) is None

    def test_a_document_note_is_judged_on_the_document_types_the_area_names(self) -> None:
        area = Area(id="a", label="A", permitted_document_types=("adr",))

        def document(kind: str) -> Note:
            return Note(id="n1", title="A", destination="document", document_type=kind)

        assert _narrowing(document("adr"), area) is None
        assert "standard is outside" in _narrowing(document("standard"), area).message  # type: ignore[union-attr]
        assert _narrowing(document("standard"), _STRATEGY) is None

    def test_an_undecided_note_is_never_warned_about(self) -> None:
        assert _narrowing(Note(id="n1", title="A"), _STRATEGY) is None

    def test_a_type_the_ontology_does_not_place_is_not_called_outside(self) -> None:
        """Without a domain there is no evidence the area excludes it."""
        assert _narrowing(_element("unheard-of"), _STRATEGY) is None


class TestTheVerdictANoteIsServedWith:
    def test_nothing_to_say_is_unverified_as_an_undecided_link_is(self) -> None:
        assert note_verdict([]).kind == "unverified"

    def test_a_narrowing_warns_and_does_not_block(self) -> None:
        verdict = note_verdict([NoteFinding(message="Outside.", narrowed_by="strategy")])

        assert (verdict.kind, verdict.blocks, verdict.narrowed_by) == ("narrowed", False, "strategy")

    @pytest.mark.parametrize("order", [(0, 1), (1, 0)])
    def test_a_blocking_finding_leads_whatever_order_they_were_made_in(self, order: tuple[int, int]) -> None:
        findings = [
            NoteFinding(message="Outside.", narrowed_by="strategy"),
            NoteFinding(message="Wrong.", blocks=True, code="E042"),
        ]

        verdict = note_verdict([findings[index] for index in order])

        assert (verdict.kind, verdict.code, verdict.blocks) == ("refused", "E042", True)
        assert verdict.message == "Wrong. Outside."
