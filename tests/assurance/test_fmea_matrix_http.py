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
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.domain.assurance.fmea_factors import OCCURRENCE_SCALE

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_CTX_PATH = "src.infrastructure.gui.routers._assurance_fmea_routes.get_assurance_context"


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
    from src.infrastructure.gui.routers._assurance_fmea_routes import fmea_router

    app = FastAPI()
    app.include_router(fmea_router)
    return TestClient(app)


@pytest.fixture()
def locked_store(tmp_path: Path) -> Any:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "locked.db"
    init_store(db_path)
    return SQLCipherAssuranceStore(db_path)


class TestTheMatrixEnvelope:
    def test_it_carries_the_occurrence_vocabulary(self, unlocked_store: Any) -> None:
        with patch(_CTX_PATH, return_value=_Context(unlocked_store)):
            body = _client(unlocked_store).get("/api/assurance/fmea").json()

        assert body["occurrence_scale"] == list(OCCURRENCE_SCALE)

    def test_the_vocabulary_keeps_the_order_the_priority_table_reads(self, unlocked_store: Any) -> None:
        """Rank, not word: a reordered list would file judgements into the wrong band."""
        with patch(_CTX_PATH, return_value=_Context(unlocked_store)):
            served = _client(unlocked_store).get("/api/assurance/fmea").json()["occurrence_scale"]

        assert served == sorted(served, key=lambda member: OCCURRENCE_SCALE.index(member))

    def test_a_locked_store_answers_423_and_serves_no_vocabulary(self, locked_store: Any) -> None:
        with patch(_CTX_PATH, return_value=_Context(locked_store)):
            resp = _client(locked_store).get("/api/assurance/fmea")

        assert resp.status_code == 423
        assert "occurrence_scale" not in resp.json()
