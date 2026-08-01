"""The failure-mode matrix REST surface: locked gating, and the vocabulary a recorder needs.

The matrix is served with the occurrence vocabulary because the surface that records a judgement has
to offer the members of the scale and nothing else. Restating them in the client would be a second
source of truth for an ordinal set whose *order* is load-bearing — the priority table reads the rank,
not the word — so a client list that drifted would place judgements in the wrong band.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.domain.assurance.fmea_factors import OCCURRENCE_SCALE
from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_CTX_PATH = "src.infrastructure.rest.routers.assurance._fmea_routes.get_assurance_context"


class _Context:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.archive = None
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        # Delegated rather than hardcoded: availability in the real context means configured *and*
        # unlocked, and a fake that always claims available lets a locked store reach a read that
        # then raises instead of answering 423.
        return bool(self.store.is_unlocked())


def _client(store: Any) -> TestClient:
    from src.infrastructure.rest.routers.assurance._fmea_routes import fmea_router

    return TestClient(build_api_app(fmea_router), raise_server_exceptions=False)


@pytest.fixture()
def locked_store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "locked.db"
    init_store(db_path)
    return SQLCipherAssuranceStore(db_path)


def _matrix_route(analysis_id: str) -> str:
    return f"/api/assurance/analyses/{analysis_id}/matrix"


def _analysis(store: Any, method: str, name: str) -> str:
    """An analysis to project. The matrix is a projection of one, so there is always one.

    Written straight to the store rather than through the use case: this fixture's context has no
    archive, and what is under test is the projection, not the audited create.
    """
    return str(store.create_analysis(name, method, tlp="TLP:WHITE"))


class TestTheMatrixEnvelope:
    def test_it_carries_the_occurrence_vocabulary(self, unlocked_store: Any) -> None:
        with patch(_CTX_PATH, return_value=_Context(unlocked_store)):
            analysis_id = _analysis(unlocked_store, "FMEA", "Pump failure modes")
            body = _client(unlocked_store).get(_matrix_route(analysis_id)).json()

        assert body["occurrence_scale"] == list(OCCURRENCE_SCALE)

    def test_the_vocabulary_keeps_the_order_the_priority_table_reads(self, unlocked_store: Any) -> None:
        """Rank, not word: a reordered list would file judgements into the wrong band."""
        with patch(_CTX_PATH, return_value=_Context(unlocked_store)):
            analysis_id = _analysis(unlocked_store, "FMEA", "Pump failure modes")
            served = _client(unlocked_store).get(
                _matrix_route(analysis_id)).json()["occurrence_scale"]

        assert served == sorted(served, key=lambda member: OCCURRENCE_SCALE.index(member))

    def test_a_locked_store_answers_423_and_serves_no_vocabulary(self, locked_store: Any) -> None:
        with patch(_CTX_PATH, return_value=_Context(locked_store)):
            resp = _client(locked_store).get(_matrix_route("AN@any"))

        assert resp.status_code == 423
        assert "occurrence_scale" not in resp.json()

    def test_a_matrix_of_another_method_is_a_typed_mismatch(self, unlocked_store: Any) -> None:
        """There is no failure-mode matrix of an STPA analysis, and an empty grid would read as
        one with nothing in it rather than one that does not exist."""
        with patch(_CTX_PATH, return_value=_Context(unlocked_store)):
            analysis_id = _analysis(unlocked_store, "STPA", "Brakes")
            resp = _client(unlocked_store).get(_matrix_route(analysis_id))

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "analysis_method_mismatch"
        assert detail["details"]["expected_method"] == "FMEA"
