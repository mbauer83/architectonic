"""The failure guidewords and matrix cell states: one source, and the distinctions they keep.

Two things are asserted beyond the obvious. The guideword vocabulary exists in exactly one place,
because the parallel UCA vocabulary once shipped in six places in three inconsistent variants and
the divergent values were accepted and then silently dropped. And the three cell states stay
three, because collapsing them would make an unexamined cell indistinguishable from one examined
and found empty — which turns an unstarted analysis into a clean bill of health.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.assurance.failure_modes import (
    ANSWERED_ASSESSMENT_STATES,
    ASSESSMENT_STATES,
    FAILURE_GUIDEWORD_SLUGS,
    FAILURE_GUIDEWORDS,
    NOT_CREDIBLE,
    PERSISTED_ASSESSMENT_STATES,
    RECORDED,
    UNTOUCHED,
    label_for,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestTheGuidewordSet:
    def test_the_five_guidewords_cover_the_ways_a_function_deviates(self) -> None:
        assert FAILURE_GUIDEWORD_SLUGS == (
            "no-function",
            "partial-function",
            "excessive-function",
            "intermittent-function",
            "unintended-function",
        )

    def test_every_guideword_asks_a_question(self) -> None:
        """The question is what an analyst is actually answering, so none may be blank."""
        for guideword in FAILURE_GUIDEWORDS:
            assert guideword.question.strip().endswith("?"), guideword.slug
            assert guideword.label.strip()

    def test_slugs_are_unique(self) -> None:
        assert len(set(FAILURE_GUIDEWORD_SLUGS)) == len(FAILURE_GUIDEWORD_SLUGS)

    def test_an_unrecognised_slug_is_shown_as_it_stands(self) -> None:
        """A failure mode carrying a guideword this software does not know is still a finding;
        rewriting it to something plausible would hide that."""
        assert label_for("no-function") == "No function"
        assert label_for("teleportation-failure") == "teleportation-failure"


class TestTheVocabularyHasOneSource:
    def test_no_other_module_writes_the_guideword_list_out(self) -> None:
        """Grep-asserted, as the UCA vocabulary is: a second copy is how the two come to differ,
        and the store's type column has no enum constraint to catch a divergent value."""
        owner = Path("src/domain/assurance/failure_modes.py")
        offenders: list[str] = []
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
            relative = path.relative_to(_REPO_ROOT)
            if relative == owner:
                continue
            text = path.read_text(encoding="utf-8")
            written_out = [slug for slug in FAILURE_GUIDEWORD_SLUGS if f'"{slug}"' in text]
            if len(written_out) > 1:
                offenders.append(f"{relative}: {written_out}")
        assert not offenders, (
            "these modules write out the guideword list instead of importing it: " + "; ".join(offenders)
        )


class TestTheThreeCellStates:
    def test_all_three_are_named(self) -> None:
        assert ASSESSMENT_STATES == (UNTOUCHED, NOT_CREDIBLE, RECORDED)

    def test_untouched_is_never_persisted(self) -> None:
        """It is the absence of a failure mode. Writing a node to record that nothing has happened
        would make coverage depend on bookkeeping rather than on content."""
        assert UNTOUCHED not in PERSISTED_ASSESSMENT_STATES
        assert PERSISTED_ASSESSMENT_STATES == (NOT_CREDIBLE, RECORDED)

    def test_a_dismissal_counts_as_an_answer(self) -> None:
        """Otherwise dismissing a cell leaves the matrix looking unfinished, and an analyst who
        wants it to look finished writes filler instead."""
        assert NOT_CREDIBLE in ANSWERED_ASSESSMENT_STATES
        assert RECORDED in ANSWERED_ASSESSMENT_STATES
        assert UNTOUCHED not in ANSWERED_ASSESSMENT_STATES

    def test_not_credible_is_distinct_from_being_out_of_scope(self) -> None:
        """`out-of-scope` (a binding_status) means outside the analysis boundary. `not-credible`
        means inside it and examined. Same-looking empty cell, different fact."""
        assert NOT_CREDIBLE != "out-of-scope"
        assert NOT_CREDIBLE not in {"bound", "unbound-pending", "out-of-scope"}
