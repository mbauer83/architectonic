"""WU-R2: proposed resolutions for a quarantining profile conflict.

The load-bearing guarantee is the last test: an operator-authored conflict is NEVER
auto-migrated. The plan sanctions auto-migration only for advancing a file byte-identical
to an older shipped profile version, and no reusable profiles ship yet — so there is no
unambiguous case, and the resolver must offer only manual moves.
"""

from __future__ import annotations

from src.domain.ontology_representation.profile_conflict_resolution import (
    propose_conflict_resolution,
    resolution_instructions,
)

_CONFLICT = "Conflicting definitions for attribute 'Score': type 'string' vs 'number'"


class TestParsing:
    def test_extracts_the_attribute_and_both_types(self) -> None:
        res = propose_conflict_resolution(_CONFLICT)
        assert res is not None
        assert (res.attribute, res.left_type, res.right_type) == ("Score", "string", "number")

    def test_a_non_type_conflict_message_yields_no_structured_resolution(self) -> None:
        assert propose_conflict_resolution("something else entirely") is None


class TestProposals:
    def test_names_all_three_moves_with_the_real_attribute(self) -> None:
        res = propose_conflict_resolution(_CONFLICT)
        assert res is not None
        joined = " ".join(res.proposals).lower()
        assert "rename" in joined
        assert "align the type" in joined
        assert "unbind" in joined
        assert all("Score" in p or "string" in p or "number" in p for p in res.proposals)

    def test_bound_profiles_are_named_in_the_unbind_proposal(self) -> None:
        res = propose_conflict_resolution(_CONFLICT, bound_profiles=("metrics", "ownership"))
        assert res is not None
        unbind = next(p for p in res.proposals if "Unbind" in p)
        assert "'metrics'" in unbind
        assert "'ownership'" in unbind

    def test_with_no_bound_profiles_the_unbind_proposal_targets_inline_or_attachment(self) -> None:
        res = propose_conflict_resolution(_CONFLICT)
        assert res is not None
        unbind = next(p for p in res.proposals if "Unbind" in p)
        assert "inline" in unbind or "attachment" in unbind


class TestRendering:
    def test_instructions_number_the_proposals(self) -> None:
        text = resolution_instructions(propose_conflict_resolution(_CONFLICT), fallback="fb")
        assert text.startswith("Resolve by one of: (1)")
        assert "(2)" in text
        assert "(3)" in text

    def test_unparsed_message_uses_the_fallback(self) -> None:
        assert resolution_instructions(None, fallback="the fallback text") == "the fallback text"


class TestNeverAutoMigrates:
    def test_a_conflict_is_never_auto_migratable(self) -> None:
        # No shipped baseline exists, so an operator-authored conflict is a human decision.
        res = propose_conflict_resolution(_CONFLICT, bound_profiles=("metrics",))
        assert res is not None
        assert res.is_auto_migratable is False
