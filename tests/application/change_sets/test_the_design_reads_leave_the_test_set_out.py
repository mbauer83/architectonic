"""Every design-set read leaves the test set out: its stressors, the ticks of them and the verdicts on them.

Regression: the reads excluded nothing, so a stressor held apart for judging joined the walk, its
kind counted towards coverage and its verdict rows were reported as unfinished design work.
"""
from pathlib import Path

from src.application.artifacts.document_schema import normalize_document_schema
from src.application.artifacts.document_table_rows import read_document_tables
from src.application.change_sets.candidate_view import CandidateView
from src.application.stress_analysis.workspace import analyse
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from tests.support.typed_table_documents import document_path, document_text, table_of, table_text

SCHEMA = normalize_document_schema("stress-analysis", STRESS_ANALYSIS_SCHEMA)
QUEUE = "SRV@1712870400.Uv9Wx9.queue"


def test_the_stressor_list_progress_coverage_and_coupling_are_of_the_design_set(tmp_path: Path) -> None:
    rows = {
        "stressors": [{"stressor": "Demand doubles", "set": "design", "kind": "economic"},
                      {"stressor": "A regulator bans the service", "set": "test", "kind": "legal"}],
        "incidence": [{"stressor": "S1", "component": QUEUE, "note": "waits"},
                      {"stressor": "S2", "component": QUEUE}, {"stressor": "S2", "component": "$ref:x"}],
        "survival": [{"stressor": "S2"}],
    }
    body = document_text(SCHEMA, {name: table_text(table_of(SCHEMA, name), held) for name, held in rows.items()})
    tables = read_document_tables(document_path(tmp_path, SCHEMA), body, SCHEMA)

    report = analyse(tables, CandidateView({QUEUE: {}}, {}))

    assert [row["id"] for row in report["stressors"]] == ["S1"]
    assert [tick["stressor"] for tick in report["incidence"]] == ["S1"]
    assert report["coupling"] == []
    assert report["coverage"]["by_kind"] == {"economic": 1}
    assert report["progress"]["unwalked"] == ["S1"]
    assert report["progress"]["unexplained_hits"] == []
    assert report["progress"]["incomplete_rows"] == []
