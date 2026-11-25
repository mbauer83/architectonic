"""A test set is held out, judged and read back over REST and MCP alike, and residuality follows the verdicts.

The round trip is the pair: verdicts and test stressors written through the document's row-batch
write, which spells the survival table, and read back by the evaluation, which reads it.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.domain.repository.repo_default_stress_perspectives import STRESS_PERSPECTIVES
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp import candidate_tools as mcp
from src.infrastructure.rest.routers import candidates, documents, state, stress_evaluation
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, documents.router, stress_evaluation.router)) as served:
            served.root = root  # type: ignore[attr-defined]
            yield served
    finally:
        reset_state_for_test()


def _start(client: TestClient, stressors: int) -> tuple[str, str]:
    started = client.post("/api/stress-analyses", json={"title": "Stress analysis — test set", "naive": {"name": "N"}})
    assert started.status_code == 200, started.text
    document = started.json()["document"]
    rows = [{"op": "add", "cells": {"stressor": f"Stressor {n}", "set": "design"}} for n in range(stressors)]
    if rows:
        _rows(client, document, "stressors", rows)
    return document, started.json()["naive_candidate"]["record"]["id"]


def _rows(client: TestClient, document: str, table: str, rows: list[dict[str, object]]) -> list[str]:
    written = client.patch(f"/api/documents/{document}/tables/{table}", json={"rows": rows, "dry_run": False})
    assert written.status_code == 200, written.text
    return list(written.json()["added_row_ids"])


def test_a_hold_out_moves_a_seeded_third_and_the_design_reads_lose_it(client: TestClient) -> None:
    document, _naive = _start(client, 6)
    path = f"/api/documents/{document}/test-set"

    planned = client.post(path + "/hold-out", json={"seed": 11})
    assert planned.status_code == 200, planned.text
    assert (planned.json()["dry_run"], planned.json()["wrote"], planned.json()["design_stressors"]) == (True, False, 6)
    assert client.get(path).json()["stressors"] == []

    held = client.post(path + "/hold-out", json={"seed": 11, "dry_run": False}).json()
    assert (held["seed"], held["held_out"], held["wrote"]) == (11, planned.json()["held_out"], True)
    assert len(held["held_out"]) == 2

    read = client.get(path).json()
    assert [row["id"] for row in read["stressors"]] == held["held_out"]
    assert read["design_stressors"] == 4
    assert read == mcp.analysis_test_set(document, str(client.root))  # type: ignore[attr-defined]
    design = {row["id"] for row in client.get(f"/api/documents/{document}/incidence").json()["stressors"]}
    assert design.isdisjoint(held["held_out"]) and len(design) == 4


def test_too_few_design_stressors_are_refused_and_nothing_moves(client: TestClient) -> None:
    document, _naive = _start(client, 2)

    refused = client.post(f"/api/documents/{document}/test-set/hold-out", json={"dry_run": False})

    assert refused.status_code == 422
    assert "at least three design stressors" in refused.json()["detail"]["message"]
    assert client.get(f"/api/documents/{document}/test-set").json()["design_stressors"] == 2


def test_verdicts_written_as_rows_read_back_as_residuality_on_every_surface(client: TestClient) -> None:
    document, naive = _start(client, 0)
    candidate = client.post("/api/change-sets", json={"record": {"name": "Adapted", "parent": naive}}).json()
    adapted = candidate["record"]["id"]
    tests = _rows(client, document, "stressors",
                  [{"op": "add", "cells": {"stressor": f"Held {n}", "set": "test"}} for n in range(3)])
    verdicts = [("naive", "fails"), ("naive", "survives"), ("naive", "fails"),
                (adapted, "survives"), (adapted, "survives"), (adapted, "degrades")]
    _rows(client, document, "survival", [
        {"op": "add", "cells": {"stressor": tests[n % 3], "architecture": who, "verdict": verdict, "usable": True,
                                "reasoning": "walked on the composed view"}}
        for n, (who, verdict) in enumerate(verdicts)
    ])

    read = client.get(f"/api/documents/{document}/test-set").json()
    standing = next(one for one in read["architectures"] if one["architecture"] == adapted)
    assert standing["residuality"] == pytest.approx((2.5 - 1) / 3)
    assert standing["strict"] == pytest.approx(1 / 3)
    assert read["stage"] == {"naive_judged": True, "adapted": True, "integrated": False,
                             "integration_judged": False}
    assert [(one["architecture"], one["verdict"]) for one in read["verdicts"]] == verdicts

    by_candidate = client.get(f"/api/change-sets/{adapted}/residuality").json()
    assert [one["document"] for one in by_candidate["analyses"]] == [document]
    assert by_candidate["analyses"][0]["residuality"] == standing["residuality"]
    assert by_candidate == mcp.change_set_read(adapted, "residuality", repo_root=str(client.root))  # type: ignore[attr-defined]


def test_the_perspectives_are_served_as_declared(client: TestClient) -> None:
    served = client.get("/api/stress-perspectives").json()

    assert served == mcp.analysis_perspectives()
    assert [one["name"] for one in served["frameworks"]] == [one.name for one in STRESS_PERSPECTIVES]
    counts = {one["id"]: len(one["perspectives"]) for one in served["frameworks"]}
    assert (counts["pestle"], counts["five-forces"], counts["business-model-canvas"]) == (6, 5, 9)
    ids = [one["id"] for framework in served["frameworks"] for one in framework["perspectives"]]
    assert len(ids) == len(set(ids))
    assert all(one["question"].endswith("?") for framework in served["frameworks"] for one in framework["perspectives"])
