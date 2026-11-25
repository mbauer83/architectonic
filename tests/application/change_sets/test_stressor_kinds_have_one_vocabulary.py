"""Stressor kinds have one vocabulary: the shipped perspectives.

Regression: the workspace also carried a list of its own ("scale", "organisation", "technology",
"actor", "regulation", "time"), which the progress read reported as unused kinds whatever the
perspectives said, and the stressors tab drew each as a warning-coloured zero.
"""
from pathlib import Path

from src.application.artifacts.document_schema import normalize_document_schema
from src.application.artifacts.document_table_rows import read_document_tables
from src.application.change_sets.candidate_view import CandidateView
from src.application.stress_analysis.evaluation import evaluate
from src.application.stress_analysis.workspace import analyse
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.domain.repository.repo_default_stress_perspectives import (
    STRESS_PERSPECTIVES,
    kinds_in_use,
    unwritten_perspectives,
)
from tests.support.typed_table_documents import document_path, document_text, table_of, table_text

SCHEMA = normalize_document_schema("stress-analysis", STRESS_ANALYSIS_SCHEMA)
EVERY = [one.id for framework in STRESS_PERSPECTIVES for one in framework.perspectives]


def _tables(tmp_path: Path, stressors: list[dict[str, str]]):
    body = document_text(SCHEMA, {"stressors": table_text(table_of(SCHEMA, "stressors"), stressors)})
    return read_document_tables(document_path(tmp_path, SCHEMA), body, SCHEMA)


def test_no_perspective_is_unwritten_while_no_stressor_names_a_kind() -> None:
    assert unwritten_perspectives(["", "  "]) == []


def test_a_kind_matches_its_perspective_whatever_its_case_and_spacing() -> None:
    unwritten = unwritten_perspectives([" Political", "LEGAL"])

    assert "pestle.political" not in unwritten and "pestle.legal" not in unwritten
    assert unwritten == [one for one in EVERY if one not in {"pestle.political", "pestle.legal"}]


def test_a_free_kind_is_allowed_counted_as_written_and_stands_for_no_perspective(tmp_path: Path) -> None:
    tables = _tables(tmp_path, [
        {"stressor": "Demand doubles", "set": "design", "kind": "economic"},
        {"stressor": "A batch job overruns", "set": "design", "kind": "Batch window"},
        {"stressor": "Nobody says", "set": "design"},
    ])

    coverage = analyse(tables, CandidateView({}, {}))["coverage"]

    assert coverage["by_kind"] == {"economic": 1, "Batch window": 1}
    assert coverage["unwritten_perspectives"] == [one for one in EVERY if one != "pestle.economic"]
    assert "unused_kinds" not in coverage


def test_the_design_coverage_never_names_a_kind_outside_the_declaration_or_counts_a_zero(tmp_path: Path) -> None:
    coverage = analyse(_tables(tmp_path, [{"stressor": "Demand doubles", "set": "design"}]), CandidateView({}, {}))[
        "coverage"
    ]

    assert coverage["by_kind"] == {}
    assert coverage["unwritten_perspectives"] == []


def test_the_test_set_reads_the_same_vocabulary_over_its_own_stressors(tmp_path: Path) -> None:
    tables = _tables(tmp_path, [
        {"stressor": "Demand doubles", "set": "design", "kind": "economic"},
        {"stressor": "A regulator bans the service", "set": "test", "kind": "legal"},
    ])

    read = evaluate(tables, integrated=[], adapted=False)

    assert read["unwritten_perspectives"] == [one for one in EVERY if one != "pestle.legal"]


def test_kinds_that_match_are_counted_as_one_under_the_first_spelling() -> None:
    assert kinds_in_use(["Legal", " legal ", "LEGAL", "batch window", "", "  "]) == {"Legal": 3, "batch window": 1}
