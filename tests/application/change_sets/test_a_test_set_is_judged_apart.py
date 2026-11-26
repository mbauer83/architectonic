"""The test set is held apart from the design work and judged at the end; residuality is read from its verdicts.

R(A) = (Y − X) / n over the usable test stressors, a *degrades* counting one half, the strict figure
counting full survivals only, and no figure until A and the naive are both judged on every usable one.
"""
from pathlib import Path
from typing import Any

import pytest

from src.application.artifacts.document_schema import normalize_document_schema
from src.application.artifacts.document_table_rows import DocumentTables, read_document_tables
from src.application.stress_analysis.evaluation import (
    ArchitectureStanding,
    architecture_standing,
    evaluate,
    held_out,
    integration_of,
    residuality,
    verdicts_of,
)
from src.application.stress_analysis.rows import in_test_set
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from tests.support.typed_table_documents import document_path, document_text, table_of, table_text

SCHEMA = normalize_document_schema("stress-analysis", STRESS_ANALYSIS_SCHEMA)


def _tables(tmp_path: Path, **rows: list[dict[str, str]]) -> DocumentTables:
    body = document_text(SCHEMA, {name: table_text(table_of(SCHEMA, name), held) for name, held in rows.items()})
    return read_document_tables(document_path(tmp_path, SCHEMA), body, SCHEMA)


def _stressors(design: int, test: int) -> list[dict[str, str]]:
    return [{"stressor": f"design {n}", "set": "design", "kind": "economic"} for n in range(design)] + [
        {"stressor": f"test {n}", "set": "test", "kind": "legal"} for n in range(test)
    ]


def _verdict(stressor: str, architecture: str, verdict: str, **more: str) -> dict[str, str]:
    return {"stressor": stressor, "architecture": architecture, "verdict": verdict, **more}


class TestTheCoefficient:
    def test_a_degraded_verdict_counts_one_half_and_the_strict_figure_none(self) -> None:
        naive = ArchitectureStanding("naive", usable=4, survives=1, degrades=0, fails=3)
        adapted = ArchitectureStanding("CAND@1", usable=4, survives=2, degrades=2, fails=0)

        assert residuality(adapted, naive) == pytest.approx(0.5)
        assert residuality(adapted, naive, strict=True) == pytest.approx(0.25)

    def test_no_figure_until_both_are_judged_on_every_usable_stressor(self) -> None:
        naive = ArchitectureStanding("naive", usable=3, survives=1, degrades=0, fails=1)
        adapted = ArchitectureStanding("CAND@1", usable=3, survives=3, degrades=0, fails=0)

        assert residuality(adapted, naive) is None
        assert residuality(naive, adapted) is None

    def test_an_empty_test_set_gives_no_figure_rather_than_a_division_by_zero(self) -> None:
        empty = ArchitectureStanding("naive", usable=0, survives=0, degrades=0, fails=0)

        assert residuality(empty, empty) is None

    def test_a_later_verdict_replaces_an_earlier_one_on_the_same_architecture(self) -> None:
        rows: list[dict[str, Any]] = [
            {"id": "T1", **_verdict("S1", "naive", "fails")},
            {"id": "T2", **_verdict("S1", "naive", "survives")},
            {"id": "T3", **_verdict("S1", "CAND@1", "fails")},
        ]

        standing = architecture_standing("naive", ["S1"], verdicts_of(rows))

        assert (standing.survives, standing.fails, standing.judged) == (1, 0, 1)


class TestTheTestSet:
    def test_the_integration_and_each_judged_candidate_stand_beside_the_naive(self, tmp_path: Path) -> None:
        tables = _tables(
            tmp_path,
            stressors=_stressors(design=1, test=3),
            survival=[
                _verdict("S2", "naive", "fails"), _verdict("S3", "naive", "survives"),
                _verdict("S4", "naive", "fails"),
                _verdict("S2", "CAND@1", "survives"), _verdict("S3", "CAND@1", "survives"),
                _verdict("S4", "CAND@1", "degrades"),
                _verdict("S2", "CAND@2", "survives"),
            ],
        )

        read = evaluate(tables, integrated=["CAND@1"], adapted=True)

        by = {one["architecture"]: one for one in read["architectures"]}
        assert list(by) == ["naive", "CAND@1", "CAND@2"]
        assert by["CAND@1"]["residuality"] == pytest.approx((2.5 - 1) / 3)
        assert by["CAND@1"]["strict"] == pytest.approx((2 - 1) / 3)
        assert (by["CAND@1"]["integrated"], by["CAND@1"]["naive_survives"]) == (True, 1)
        assert "residuality" not in by["naive"]
        assert (by["CAND@2"]["judged"], by["CAND@2"]["usable"], "residuality" in by["CAND@2"]) == (1, 3, False)
        assert read["stage"] == {"naive_judged": True, "adapted": True, "integrated": True, "integration_judged": True}
        assert [row["id"] for row in read["stressors"]] == ["S2", "S3", "S4"]

    def test_candidates_integrated_apart_are_judged_together_as_the_integration(self, tmp_path: Path) -> None:
        tables = _tables(
            tmp_path,
            stressors=_stressors(design=1, test=2),
            survival=[
                _verdict("S2", "naive", "fails"), _verdict("S3", "naive", "fails"),
                _verdict("S2", "CAND@1", "survives"), _verdict("S3", "CAND@1", "fails"),
                _verdict("S2", "integration", "survives"), _verdict("S3", "integration", "degrades"),
            ],
        )

        read = evaluate(tables, integrated=["CAND@1", "CAND@2"], integration="integration", adapted=True)

        by = {one["architecture"]: one for one in read["architectures"]}
        assert list(by) == ["naive", "CAND@1", "CAND@2", "integration"]
        assert by["integration"]["residuality"] == pytest.approx((1.5 - 0) / 2)
        assert by["integration"]["strict"] == pytest.approx(1 / 2)
        assert read["stage"]["integration_judged"] is True

    def test_the_integration_stands_unjudged_until_it_is_judged(self, tmp_path: Path) -> None:
        tables = _tables(
            tmp_path, stressors=_stressors(design=1, test=1),
            survival=[_verdict("S2", "naive", "fails"), _verdict("S2", "CAND@1", "survives")],
        )

        read = evaluate(tables, integrated=["CAND@1", "CAND@2"], integration="integration", adapted=True)

        by = {one["architecture"]: one for one in read["architectures"]}
        assert (by["integration"]["judged"], "residuality" in by["integration"]) == (0, False)
        assert read["stage"]["integration_judged"] is False


class TestWhatStandsForTheIntegration:
    def test_an_integrated_candidate_whose_stack_holds_every_other_one_is_the_integration(self) -> None:
        stacks = {"CAND@1": ["CAND@1"], "CAND@2": ["CAND@1", "CAND@2"]}

        assert integration_of(["CAND@1", "CAND@2"], stacks.__getitem__) == "CAND@2"

    def test_candidates_integrated_apart_are_stood_for_by_the_integration(self) -> None:
        stacks = {"CAND@1": ["CAND@1"], "CAND@2": ["CAND@2"]}

        assert integration_of(["CAND@1", "CAND@2"], stacks.__getitem__) == "integration"

    def test_nothing_stands_for_it_while_nothing_is_integrated(self) -> None:
        assert integration_of([], lambda ref: [ref]) is None


class TestWhatTheTestSetCounts:
    def test_a_stressor_is_held_apart_only_where_its_set_says_test(self, tmp_path: Path) -> None:
        # The one reading of the convention; the GUI reads the evaluation's `stressors` rather than the rows.
        stressors = [{"stressor": "a", "set": "test"}, {"stressor": "b", "set": "design"}, {"stressor": "c"}]

        read = evaluate(_tables(tmp_path, stressors=stressors), integrated=[], adapted=False)

        assert [in_test_set(row) for row in stressors] == [True, False, False]
        assert [one["id"] for one in read["stressors"]] == ["S1"]

    def test_a_struck_stressor_leaves_the_denominator_with_its_reason(self, tmp_path: Path) -> None:
        tables = _tables(
            tmp_path,
            stressors=_stressors(design=0, test=2),
            survival=[
                {"stressor": "S1", "architecture": "naive", "usable": "false", "reasoning": "contradicts itself"},
                _verdict("S2", "naive", "fails"), _verdict("S2", "CAND@1", "survives"),
            ],
        )

        read = evaluate(tables, integrated=[], adapted=True)

        assert read["stressors"][0] == {"id": "S1", "stressor": "test 0", "kind": "legal", "usable": False,
                                        "unusable_reason": "contradicts itself"}
        candidate = read["architectures"][1]
        assert (candidate["usable"], candidate["residuality"]) == (1, pytest.approx(1.0))

    def test_a_verdict_on_a_design_stressor_is_not_a_test_verdict(self, tmp_path: Path) -> None:
        tables = _tables(tmp_path, stressors=_stressors(design=1, test=1),
                         survival=[_verdict("S1", "CAND@1", "survives")])

        read = evaluate(tables, integrated=[], adapted=False)

        assert read["verdicts"] == []
        assert [one["architecture"] for one in read["architectures"]] == ["naive"]


class TestTheHoldOut:
    def test_a_third_is_drawn_in_document_order_and_the_same_seed_draws_it_again(self) -> None:
        design = [f"S{n}" for n in range(1, 13)]

        drawn = held_out(design, seed=42)

        assert len(drawn) == 4
        assert list(drawn) == sorted(drawn, key=design.index)
        assert held_out(design, seed=42) == drawn
        assert any(held_out(design, seed=seed) != drawn for seed in range(1, 6))

    def test_fewer_than_three_design_stressors_cannot_give_a_third(self) -> None:
        with pytest.raises(ValueError, match="at least three design stressors"):
            held_out(["S1", "S2"], seed=1)
