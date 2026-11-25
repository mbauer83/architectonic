"""A form's default name for a new document is asked of the rule that refuses a taken one.

Two analyses of the same architecture got the same default title, and the second was refused when it
was started: document type and name are unique. The free name is the rule's own answer, numbered.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS_SCHEMA
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import candidates, document_titles, state
from tests.support.api_app import build_api_app
from tests.support.rest_state import reset_state_for_test
from tests.support.typed_table_documents import repository_in

TITLE = "Stress analysis — One Enterprise Repository"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = repository_in(tmp_path)
    (root / ".arch-repo/documents/stress-analysis.json").write_text(json.dumps(STRESS_ANALYSIS_SCHEMA))
    state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    try:
        with TestClient(build_api_app(candidates.router, document_titles.router)) as served:
            yield served
    finally:
        reset_state_for_test()


def _free(client: TestClient, title: str = TITLE) -> str:
    answer = client.get("/api/document-types/stress-analysis/free-title", params={"title": title})
    assert answer.status_code == 200, answer.text
    return str(answer.json()["title"])


def _start(client: TestClient, title: str) -> int:
    started = client.post("/api/stress-analyses", json={"title": title, "naive": {"name": "Naive architecture"}})
    return started.status_code


def test_a_name_no_document_holds_is_free_as_it_is(client: TestClient) -> None:
    assert _free(client) == TITLE


def test_a_second_analysis_of_the_same_architecture_is_offered_a_numbered_name_it_can_start_with(
    client: TestClient,
) -> None:
    assert _start(client, _free(client)) == 200
    second = _free(client)

    assert second == f"{TITLE} (2)"
    assert _start(client, TITLE) == 422  # the rule the free name was asked of
    assert _start(client, second) == 200
    assert _free(client) == f"{TITLE} (3)"


def test_an_undeclared_document_type_is_not_found(client: TestClient) -> None:
    answer = client.get("/api/document-types/no-such-type/free-title", params={"title": "X"})
    assert answer.status_code == 404
