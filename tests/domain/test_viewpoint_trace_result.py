"""Status registry precedence + verdict mapping, obligation collapse/distinctness, and the
discriminated PatternResult union."""

from __future__ import annotations

import dataclasses

from src.domain.viewpoints.viewpoint_trace_result import (
    AuthoritativePatternResult,
    Coverage,
    DiagnosticPatternResult,
    MissingOutcomeObligation,
    MissingRequirementObligation,
    ShortcutObligation,
    TerminalObligation,
    is_missing_obligation,
    resolve_status,
    verdict_of,
)


class TestStatusRegistry:
    def test_precedence_worst_wins(self) -> None:
        assert resolve_status(frozenset({"ok", "shortcut", "cycle"})) == "cycle"
        assert resolve_status(frozenset({"ok", "shortcut"})) == "shortcut"
        assert resolve_status(frozenset({"partial_branches", "no_trace"})) == "partial_branches"
        assert resolve_status(frozenset({"ok"})) == "ok"

    def test_empty_status_is_not_applicable(self) -> None:
        assert resolve_status(frozenset()) == "not_applicable"

    def test_verdict_mapping(self) -> None:
        assert verdict_of("ok") == "pass"
        assert verdict_of("not_applicable") == "not_applicable"
        for gap in ("shortcut", "incomplete_branch", "partial_branches", "no_trace", "ambiguous_link", "cycle"):
            assert verdict_of(gap) == "gap"


class TestObligations:
    def test_duplicate_terminal_obligations_collapse_in_a_set(self) -> None:
        a = TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@1")
        b = TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@1")
        assert len({a, b}) == 1

    def test_same_requirement_via_two_outcomes_are_two_obligations(self) -> None:
        a = TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@1")
        b = TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@2")
        assert len({a, b}) == 2

    def test_canonical_tuples_carry_the_leading_tag(self) -> None:
        assert TerminalObligation("G", "R", "O").canonical() == ("requirement", "G", "O", "R")
        assert TerminalObligation("O", "R").canonical() == ("requirement", "O", "R")
        assert ShortcutObligation("G", "R").canonical() == ("shortcut", "G", "R")
        assert MissingRequirementObligation("G", "O").canonical() == ("missing-requirement", "G", "O")
        assert MissingOutcomeObligation("G").canonical() == ("missing-outcome", "G")

    def test_serialized_obligations_carry_their_tag(self) -> None:
        # Regression: obligations reached the wire as untagged field bags, so a consumer could
        # not tell a shortcut from an outcome-less terminal, nor missing-outcome from
        # missing-requirement (they differ only by a key's presence). The obligation contract requires TAGGED
        # tuples, so the discriminator is a real field that survives dataclasses.asdict.
        assert dataclasses.asdict(TerminalObligation("G", "R"))["kind"] == "requirement"
        assert dataclasses.asdict(ShortcutObligation("G", "R"))["kind"] == "shortcut"
        assert dataclasses.asdict(MissingRequirementObligation("G", "O"))["kind"] == "missing-requirement"
        assert dataclasses.asdict(MissingOutcomeObligation("G"))["kind"] == "missing-outcome"

    def test_shortcut_and_outcome_less_terminal_are_distinguishable_when_serialized(self) -> None:
        terminal = dataclasses.asdict(TerminalObligation("G", "R"))
        shortcut = dataclasses.asdict(ShortcutObligation("G", "R"))
        assert terminal["kind"] != shortcut["kind"]

    def test_missing_obligation_classification(self) -> None:
        assert is_missing_obligation(MissingOutcomeObligation("G"))
        assert is_missing_obligation(MissingRequirementObligation("G", "O"))
        assert not is_missing_obligation(TerminalObligation("G", "R", "O"))
        assert not is_missing_obligation(ShortcutObligation("G", "R"))


class TestPatternResultUnion:
    def test_authoritative_result_shape(self) -> None:
        result = AuthoritativePatternResult(
            verdict="gap", status_code="incomplete_branch", coverage=Coverage(1, 2),
            incomplete_branch_count=1, failing_obligations=(MissingRequirementObligation("G", "O"),),
            failing_overflow=0, last_satisfied_ids=("REQ@1",), missing_expected=("requirement",), shortcut=False,
        )
        assert result.role == "authoritative"
        assert result.coverage.applicable == 2

    def test_diagnostic_result_status_is_the_observation(self) -> None:
        diag = DiagnosticPatternResult(observation="none_observed", last_satisfied_ids=())
        assert diag.role == "diagnostic"
        assert diag.status_code == "none_observed"
