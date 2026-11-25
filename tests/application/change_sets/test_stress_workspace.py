"""Promotion stalls between the engagement and enterprise repositories while requests queue."""
from pathlib import Path

from src.application.artifacts.document_schema import normalize_document_schema
from src.application.artifacts.document_table_rows import read_document_tables
from src.application.change_sets.candidate_view import CandidateView
from src.application.stress_analysis.workspace import analyse
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from tests.support.typed_table_documents import document_path, document_text, table_of, table_text

ENTERPRISE = "BOB@1712870400.6Uok0b.enterprise-repository"
ENGAGEMENT = "BOB@1712870400.so7gfN.engagement-repository"
SERVICE = "SRV@1712870400.Uv9Wx9.repository-promotion-service"


def test_promotion_outage_tracks_the_naive_queue_even_after_it_is_removed(tmp_path: Path) -> None:
    schema = normalize_document_schema("stress-analysis", STRESS_ANALYSIS_SCHEMA)
    rows = {
        "stressors": [
            {"stressor": "Promotion service unavailable", "kind": "outage", "set": "design",
             "subject": "$ref:queue", "consequence": "Promotions accumulate", "end_state": "E1"},
        ],
        "end-states": [{"end_state": "Enterprise consumers see the previous architecture"}],
        "incidence": [{"stressor": "S1", "component": c, "note": "Pending promotion"} for c in (SERVICE, "$ref:queue")],
    }
    body = document_text(schema, {k: table_text(table_of(schema, k), v) for k, v in rows.items()})
    tables = read_document_tables(document_path(tmp_path, schema), body, schema)
    view = CandidateView({ref: {} for ref in (ENTERPRISE, ENGAGEMENT, SERVICE, "$ref:queue")}, {})
    report = analyse(tables, view)
    assert report["stressors"][0]["missing_elements"] == []
    assert report["coupling"] == [{"left": "$ref:queue", "right": SERVICE, "count": 1}]
    assert report["coverage"]["by_kind"] == {"outage": 1}
    assert "pestle.political" in report["coverage"]["unwritten_perspectives"]
    assert report["progress"]["without_adaptation"] == ["E1"]
    del view.entities["$ref:queue"]
    assert analyse(tables, view)["stressors"][0]["missing_elements"] == ["$ref:queue"]
