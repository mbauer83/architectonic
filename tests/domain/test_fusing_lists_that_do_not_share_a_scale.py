"""Reciprocal rank fusion, as a function: the cases the plan named, and the properties it rests on.

Three retrievers answer a search and their scores do not compare — the codebase says so about its own
full-text scales, and orders kinds by round-robin *because* a global sort is not available. Fusion is
the rank-based form of that, so what has to hold is about ranks and never about magnitudes.

The tie-break is asserted as **determinism**, not as quality. A tie-break preferring whichever
candidate placed highest in some single list would be a claim that it ranks better, and that belongs
to a labelled query suite that can measure it.
"""

from __future__ import annotations

import pytest

from src.domain.rank_fusion import RRF_K, fuse_keeping_the_lead, fuse_ranked_lists
from src.domain.search_records import SearchCandidate


def entity(name: str) -> SearchCandidate:
    return SearchCandidate(record_type="entity", artifact_id=f"APP@1.{name}")


def document(name: str) -> SearchCandidate:
    return SearchCandidate(record_type="document", artifact_id=f"ADR@1.{name}")


def _order(fused) -> list[str]:
    return [f.candidate.artifact_id for f in fused]


class TestTheCasesThePlanNamed:
    def test_identical_lists_keep_their_order(self) -> None:
        ranked = [entity("a"), entity("b"), entity("c")]

        fused = fuse_ranked_lists([ranked, ranked])

        assert _order(fused) == ["APP@1.a", "APP@1.b", "APP@1.c"]

    def test_disjoint_lists_interleave_by_rank(self) -> None:
        """Nothing appears twice, so rank alone decides: both firsts, then both seconds."""
        fused = fuse_ranked_lists(
            [[entity("a"), entity("b")], [document("x"), document("y")]]
        )

        assert set(_order(fused)[:2]) == {"APP@1.a", "ADR@1.x"}
        assert set(_order(fused)[2:]) == {"APP@1.b", "ADR@1.y"}

    def test_an_empty_list_contributes_nothing(self) -> None:
        ranked = [entity("a"), entity("b")]

        assert _order(fuse_ranked_lists([ranked, []])) == _order(fuse_ranked_lists([ranked]))

    def test_no_lists_at_all_fuse_to_nothing(self) -> None:
        assert fuse_ranked_lists([]) == []
        assert fuse_ranked_lists([[], []]) == []

    def test_appearing_in_two_lists_beats_placing_highly_in_one(self) -> None:
        """The property fusion exists for. `b` is second in both; `a` is first in one and absent
        from the other."""
        fused = fuse_ranked_lists(
            [
                [entity("a"), entity("b")],
                [document("x"), entity("b")],
            ]
        )

        assert _order(fused)[0] == "APP@1.b"


class TestKsEffect:
    def test_a_large_k_flattens_the_difference_between_ranks(self) -> None:
        """k decides how far down two lists a candidate may be and still beat someone else's first.

        Measured while writing this, because the obvious case does not depend on k at all: rank two
        in both lists beats rank one in one list for *every* k, since `1/(k+1) > 2/(k+2)` has no
        solution. k bites when the twice-found candidate is far down — at rank five in both, k=60
        still prefers it and k=1 does not.
        """
        far_down = [
            [entity("a"), *(document(f"pad{i}") for i in range(3)), entity("b")],
            [document("x"), *(document(f"other{i}") for i in range(3)), entity("b")],
        ]

        assert _order(fuse_ranked_lists(far_down, k=60))[0] == "APP@1.b"
        assert _order(fuse_ranked_lists(far_down, k=1))[0] == "APP@1.a"

    def test_two_lists_beat_one_at_the_top_whatever_k_is(self) -> None:
        """The property that holds for every k, stated so the case above is not read as general."""
        lists = [[entity("a"), entity("b")], [document("x"), entity("b")]]

        for k in (1, 2, 10, 60, 1000):
            assert _order(fuse_ranked_lists(lists, k=k))[0] == "APP@1.b", k

    def test_k_defaults_to_the_papers_value(self) -> None:
        lists = [[entity("a"), entity("b")]]

        assert fuse_ranked_lists(lists) == fuse_ranked_lists(lists, k=RRF_K)
        assert RRF_K == 60

    def test_k_below_one_is_refused_rather_than_dividing_by_zero(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            fuse_ranked_lists([[entity("a")]], k=0)


class TestTheIdentityIsThePair:
    def test_one_id_under_two_kinds_stays_two_candidates(self) -> None:
        """Fusing bare strings would collapse these, and let a hit past a caller's kind policy."""
        same_id = "X@1.shared"
        as_entity = SearchCandidate(record_type="entity", artifact_id=same_id)
        as_document = SearchCandidate(record_type="document", artifact_id=same_id)

        fused = fuse_ranked_lists([[as_entity], [as_document]])

        assert len(fused) == 2
        assert {f.candidate.record_type for f in fused} == {"entity", "document"}

    def test_a_repeat_within_one_list_states_one_opinion(self) -> None:
        """Otherwise a retriever could inflate a candidate by returning it twice."""
        once = fuse_ranked_lists([[entity("a"), entity("b")]])
        twice = fuse_ranked_lists([[entity("a"), entity("a"), entity("b")]])

        assert [f.score for f in once] == pytest.approx([f.score for f in twice])


class TestDeterminism:
    def test_a_tie_is_broken_the_same_way_every_time(self) -> None:
        """Two candidates at the same rank in different lists tie exactly. The order must not depend
        on dict iteration, insertion or the machine."""
        lists = [[entity("b")], [entity("a")]]

        orders = {tuple(_order(fuse_ranked_lists(lists))) for _ in range(20)}

        assert len(orders) == 1

    def test_ties_break_by_the_existing_kind_order_then_the_id(self) -> None:
        """The kind order search already has — not a second one invented here."""
        fused = fuse_ranked_lists([[document("x")], [entity("a")]])

        assert [f.candidate.record_type for f in fused] == ["entity", "document"]

    def test_the_same_ties_within_one_kind_break_by_id(self) -> None:
        fused = fuse_ranked_lists([[entity("z")], [entity("a")]])

        assert _order(fused) == ["APP@1.a", "APP@1.z"]

    def test_input_order_of_the_lists_does_not_change_the_result(self) -> None:
        """Fusion is symmetric in its lists; a caller passing them in another order is not stating
        a preference."""
        first = [entity("a"), entity("b")]
        second = [document("x"), entity("b")]

        assert _order(fuse_ranked_lists([first, second])) == _order(fuse_ranked_lists([second, first]))


def test_the_score_is_the_sum_of_reciprocal_ranks() -> None:
    """Stated once, so the formula is pinned rather than only its consequences."""
    fused = fuse_ranked_lists([[entity("a"), entity("b")], [entity("b")]], k=60)
    by_id = {f.candidate.artifact_id: f.score for f in fused}

    assert by_id["APP@1.a"] == pytest.approx(1 / 61)
    assert by_id["APP@1.b"] == pytest.approx(1 / 62 + 1 / 61)


class TestKeepingOneListsLead:
    """`fuse_keeping_the_lead`: RRF, except that one named list's first place is not taken away."""

    #: The shape the labelled suite lost a query to: the anchor's lead is sixth in the other list, a
    #: candidate second in both outscores it, and one sixth-and-first ties it.
    ANCHOR = [entity("lead"), entity("both"), *(entity(f"a{i}") for i in range(3)), entity("other-lead")]
    OTHER = [entity("other-lead"), entity("both"), *(entity(f"b{i}") for i in range(3)), entity("lead")]

    def test_plain_rrf_takes_the_lead_away_at_every_k(self) -> None:
        """Why the variant exists: no k keeps it, because RRF is convex in rank."""
        for k in (1, 2, 5, 10, 60, 1000):
            assert _order(fuse_ranked_lists([self.ANCHOR, self.OTHER], k=k))[0] != "APP@1.lead", k

    def test_the_anchors_lead_stays_first(self) -> None:
        for k in (1, 10, 60):
            assert _order(fuse_keeping_the_lead(self.ANCHOR, [self.OTHER], k=k))[0] == "APP@1.lead", k

    def test_a_lead_the_other_list_never_found_stays_first(self) -> None:
        anchor = [entity("lead"), entity("x"), entity("y")]
        other = [entity("x"), entity("y")]

        assert _order(fuse_keeping_the_lead(anchor, [other]))[0] == "APP@1.lead"

    def test_everything_below_the_lead_keeps_rrfs_order_and_scores(self) -> None:
        kept = fuse_keeping_the_lead(self.ANCHOR, [self.OTHER])
        plain = [f for f in fuse_ranked_lists([self.ANCHOR, self.OTHER]) if f.candidate != entity("lead")]

        assert kept[1:] == plain

    def test_the_leads_score_is_the_highest_and_unshared(self) -> None:
        """Scores, not only positions: the ranking policy re-sorts a kind by score."""
        kept = fuse_keeping_the_lead(self.ANCHOR, [self.OTHER], k=60)

        assert kept[0].score == pytest.approx(2 / 61)
        assert all(entry.score < kept[0].score for entry in kept[1:])

    def test_where_rrf_already_leads_with_it_nothing_changes(self) -> None:
        anchor = [entity("a"), entity("b")]
        other = [entity("a"), entity("c")]

        assert fuse_keeping_the_lead(anchor, [other]) == fuse_ranked_lists([anchor, other])

    def test_an_empty_anchor_is_plain_rrf(self) -> None:
        other = [entity("a"), entity("b")]

        assert fuse_keeping_the_lead([], [other]) == fuse_ranked_lists([[], other])

    def test_with_nothing_else_to_fuse_the_anchor_is_its_own_order(self) -> None:
        anchor = [entity("a"), entity("b")]

        assert fuse_keeping_the_lead(anchor, [[]]) == fuse_ranked_lists([anchor])
