"""An obligation's citation has one stored form, and the forms before it can be brought to it.

Three spellings preceded `source` and `provision`. These hold what the rewrite does with each, and
the two things it must not do: choose between two values that disagree, and invent a reading of a
`cites` that is not `source:provision`.
"""

from __future__ import annotations

import pytest

from src.domain.assurance.obligation_citation import (
    ObligationCitation,
    citation_of,
    rewrite_superseded,
    source_key,
    superseded_attributes_in,
)


class TestTheCurrentForm:
    def test_it_is_read_from_source_and_provision(self) -> None:
        assert citation_of({"source": " EU AI Act ", "provision": "Art. 12"}) == ObligationCitation(
            source="EU AI Act", provision="Art. 12"
        )

    @pytest.mark.parametrize("former", [{"scheme": "ISO26262", "code": "6-8"}, {"cites": "ISO26262:6-8"}])
    def test_a_former_spelling_is_not_read_as_a_citation(self, former: dict[str, object]) -> None:
        assert citation_of(former) == ObligationCitation(source="", provision="")
        assert superseded_attributes_in(former)

    def test_a_value_that_is_not_text_states_nothing(self) -> None:
        assert citation_of({"source": 26262, "provision": None}) == ObligationCitation("", "")


class TestBringingAFormerSpellingToIt:
    def test_the_wizards_pair_is_renamed(self) -> None:
        rewrite = rewrite_superseded({"scheme": "ISO26262", "code": "6-8", "status": "open"})

        assert rewrite.attributes == {"source": "ISO26262", "provision": "6-8", "status": "open"}
        assert rewrite.moved == (("scheme", "source"), ("code", "provision"))
        assert rewrite.left_in_place == ()

    def test_the_hand_written_pair_is_renamed(self) -> None:
        rewrite = rewrite_superseded({"framework": "EU AI Act", "clause": "Art. 12", "status": "open"})

        assert rewrite.attributes == {"source": "EU AI Act", "provision": "Art. 12", "status": "open"}
        assert rewrite.moved == (("framework", "source"), ("clause", "provision"))
        assert rewrite.left_in_place == ()

    def test_both_former_pairs_agreeing_become_one_citation(self) -> None:
        rewrite = rewrite_superseded({"scheme": "GDPR", "code": "Art. 5", "framework": "GDPR", "clause": "Art. 5"})

        assert rewrite.attributes == {"source": "GDPR", "provision": "Art. 5"}
        assert rewrite.left_in_place == ()

    def test_of_two_former_pairs_that_disagree_the_second_stays(self) -> None:
        rewrite = rewrite_superseded({"scheme": "GDPR", "code": "Art. 5", "framework": "ISO 27001", "clause": "A.5"})

        assert rewrite.attributes == {
            "source": "GDPR", "provision": "Art. 5", "framework": "ISO 27001", "clause": "A.5",
        }
        assert [former for former, _ in rewrite.left_in_place] == ["framework", "clause"]

    @pytest.mark.parametrize("former", [{"framework": "ISO26262"}, {"clause": "6-8"}])
    def test_a_hand_written_attribute_is_recognised_as_former(self, former: dict[str, object]) -> None:
        assert superseded_attributes_in(former) == tuple(former)

    def test_a_combined_citation_is_split_at_the_first_colon(self) -> None:
        """A provision may hold a colon of its own; a source cannot be told from one that does."""
        rewrite = rewrite_superseded({"cites": "ISO26262: 6-8:2018"})

        assert rewrite.attributes == {"source": "ISO26262", "provision": "6-8:2018"}

    def test_applying_it_again_changes_nothing(self) -> None:
        once = rewrite_superseded({"scheme": "GDPR", "code": "Art. 5", "cites": "GDPR:Art. 5"})
        twice = rewrite_superseded(once.attributes)

        assert once.attributes == {"source": "GDPR", "provision": "Art. 5"}
        assert not twice.changes_something
        assert twice.attributes == once.attributes

    def test_attributes_already_current_are_untouched(self) -> None:
        current = {"source": "EU AI Act", "provision": "Art. 12"}

        rewrite = rewrite_superseded(current)

        assert not rewrite.changes_something
        assert rewrite.attributes == current

    @pytest.mark.parametrize("unreadable", ["ISO26262", ":6-8", "ISO26262:", "", 7])
    def test_a_cites_that_is_not_source_and_provision_stays(self, unreadable: object) -> None:
        rewrite = rewrite_superseded({"cites": unreadable})

        assert rewrite.attributes == {"cites": unreadable}
        assert not rewrite.changes_something
        assert [former for former, _ in rewrite.left_in_place] == ["cites"]

    def test_a_former_value_that_disagrees_with_the_current_one_stays(self) -> None:
        """Which of the two is right is not something a rename can know."""
        rewrite = rewrite_superseded({"scheme": "ISO26262", "source": "ISO 21434"})

        assert rewrite.attributes == {"scheme": "ISO26262", "source": "ISO 21434"}
        assert [former for former, _ in rewrite.left_in_place] == ["scheme"]

    def test_a_combined_citation_half_of_which_disagrees_moves_neither_half(self) -> None:
        rewrite = rewrite_superseded({"cites": "ISO26262:6-8", "provision": "4-7"})

        assert rewrite.attributes == {"cites": "ISO26262:6-8", "provision": "4-7"}
        assert "source" not in rewrite.attributes

    def test_a_former_value_that_agrees_with_the_current_one_is_dropped(self) -> None:
        rewrite = rewrite_superseded({"scheme": "GDPR", "source": "GDPR"})

        assert rewrite.attributes == {"source": "GDPR"}


class TestComparingSources:
    @pytest.mark.parametrize("written", ["ISO 26262", "ISO26262", "iso-26262", " Iso/26262 "])
    def test_one_document_written_several_ways_is_one_source(self, written: str) -> None:
        assert source_key(written) == source_key("ISO26262")

    def test_different_documents_stay_different(self) -> None:
        assert source_key("ISO 26262") != source_key("ISO 21434")
