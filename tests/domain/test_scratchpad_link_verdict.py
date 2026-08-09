"""What the canvas may say about a drawn link.

Two tiers, and the split is a *consequence* of what the ontology declares about its classification
levels rather than a rule stated here: the level that keys relationships refuses (E126, blocks), a
level that only narrows them warns (W128, does not block). B3 exists so this module can read that
rather than restate it.

Many cases, deliberately. This vocabulary is what a modal renders to someone in the middle of
drawing a link, and the difference between "the ontology has no such relation" and "this
specialization says not here" is the difference between changing a type and accepting a warning.
"""

from __future__ import annotations

from src.domain.scratchpad import Endpoint, LinkVerdict, verify_link

#: A tiny ontology: a requirement realizes an outcome, a capability serves a goal.
_PERMITTED = {
    ("requirement", "archimate-realization", "outcome"),
    ("outcome", "archimate-realization", "goal"),
    ("capability", "archimate-serving", "goal"),
}


def _permits(source: str, conn: str, target: str) -> bool:
    return (source, conn, target) in _PERMITTED


def _permitted_types(source: str, target: str) -> tuple[str, ...]:
    return tuple(conn for (s, conn, t) in sorted(_PERMITTED) if s == source and t == target)


def _element(element_type: str, specialization: str | None = None) -> Endpoint:
    return Endpoint(destination="element", element_type=element_type, specialization=specialization)


def _verify(source: Endpoint, target: Endpoint, conn: str | None, **kwargs: object) -> LinkVerdict:
    return verify_link(
        source, target, connection_type=conn,
        permits=_permits, permitted_types=_permitted_types, **kwargs,  # type: ignore[arg-type]
    )


class TestVerificationDoesNotNag:
    def test_an_undecided_end_is_not_yet_a_question(self) -> None:
        verdict = _verify(_element("requirement"), Endpoint(), "archimate-realization")

        assert verdict.kind == "unverified"
        assert not verdict.is_settled

    def test_two_undecided_ends_say_nothing_either(self) -> None:
        assert _verify(Endpoint(), Endpoint(), None).kind == "unverified"

    def test_two_documents_have_no_model_meaning_and_stay_a_scratchpad_link(self) -> None:
        document = Endpoint(destination="document", document_type="budget")

        assert _verify(document, document, None).kind == "unverified"


class TestTheKeyingTierRefuses:
    def test_an_unpermitted_triple_is_refused_as_e126(self) -> None:
        verdict = _verify(_element("goal"), _element("capability"), "archimate-serving")

        assert verdict.kind == "refused"
        assert verdict.code == "E126"
        assert verdict.blocks

    def test_it_leads_with_reversing_the_link_when_the_reverse_is_permitted(self) -> None:
        """ArchiMate relations are ordered triples, and dragging the wrong way is the commonest
        slip there is. One click fixes it, and it is almost certainly what was meant."""
        verdict = _verify(_element("goal"), _element("capability"), "archimate-serving")

        assert verdict.reverse_permitted
        assert "The reverse is." in verdict.message

    def test_it_does_not_offer_reversal_when_the_reverse_is_also_wrong(self) -> None:
        verdict = _verify(_element("goal"), _element("requirement"), "archimate-serving")

        assert verdict.kind == "refused"
        assert not verdict.reverse_permitted

    def test_a_permitted_triple_passes(self) -> None:
        verdict = _verify(_element("requirement"), _element("outcome"), "archimate-realization")

        assert verdict.kind == "permitted"
        assert not verdict.blocks


class TestBothEndsTypedButTheLinkIsNot:
    def test_it_offers_what_the_pair_permits(self) -> None:
        verdict = _verify(_element("requirement"), _element("outcome"), None)

        assert verdict.kind == "unverified"
        assert verdict.alternatives == ("archimate-realization",)

    def test_a_pair_with_no_permitted_relation_is_worth_saying_before_they_go_looking(self) -> None:
        verdict = _verify(_element("goal"), _element("capability"), None)

        assert verdict.kind == "refused"
        assert verdict.code == "E126"
        assert verdict.reverse_permitted


class TestTheNarrowingTierWarns:
    def _narrows(self, slug: str, conn: str, source: str, target: str) -> str | None:
        return slug if slug == "strict" else None

    def test_a_specialization_that_forbids_the_pair_warns_rather_than_blocking(self) -> None:
        """The relation exists; this specialization says it does not apply here. That is a
        different statement from 'the ontology has no such relation', and a different remedy."""
        verdict = _verify(
            _element("requirement", "strict"), _element("outcome"),
            "archimate-realization", narrows=self._narrows,
        )

        assert verdict.kind == "narrowed"
        assert verdict.code == "W128"
        assert not verdict.blocks
        assert verdict.narrowed_by == "strict"

    def test_a_specialization_that_permits_it_leaves_the_verdict_alone(self) -> None:
        verdict = _verify(
            _element("requirement", "lenient"), _element("outcome"),
            "archimate-realization", narrows=self._narrows,
        )

        assert verdict.kind == "permitted"

    def test_either_end_s_specialization_can_narrow(self) -> None:
        verdict = _verify(
            _element("requirement"), _element("outcome", "strict"),
            "archimate-realization", narrows=self._narrows,
        )

        assert verdict.kind == "narrowed"

    def test_a_meta_ontology_with_no_narrowing_tier_simply_has_none(self) -> None:
        """`narrows` is optional because the narrowing level is exactly the part a meta-ontology
        may declare it does not have."""
        verdict = _verify(_element("requirement", "strict"), _element("outcome"), "archimate-realization")

        assert verdict.kind == "permitted"


class TestElementToDocument:
    def test_it_becomes_a_reference_rather_than_a_connection(self) -> None:
        """ArchiMate has no document element; the link is realizable as a document→model
        reference, which the document records."""
        verdict = _verify(
            _element("requirement"), Endpoint(destination="document", document_type="budget"), None
        )

        assert verdict.kind == "reference"
        assert not verdict.blocks

    def test_the_direction_drawn_does_not_matter(self) -> None:
        """References run one way and are recorded on the document, so the canvas must not care
        which way the user happened to drag."""
        document = Endpoint(destination="document", document_type="budget")

        assert _verify(document, _element("requirement"), None).kind == "reference"

    def test_a_document_linked_to_an_undecided_note_is_not_yet_anything(self) -> None:
        document = Endpoint(destination="document", document_type="budget")

        assert _verify(document, Endpoint(), None).kind == "unverified"
