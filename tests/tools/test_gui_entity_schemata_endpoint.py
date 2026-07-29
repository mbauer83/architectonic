"""REST tests for ``GET /api/entity-schemata``: the authoring form's attribute schema
must be the *effective* schema — base type merged with the selected specialization's
contributed attributes — matching what the verifier validates against."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_repository import ArtifactRepository
from src.application.artifact_schema import clear_schema_cache
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router

httpx = pytest.importorskip("httpx")


def _write_schema(repo_root: Path, filename: str, schema: dict) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / filename).write_text(json.dumps(schema), encoding="utf-8")


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


@pytest.fixture()
def client(engagement_root: Path):
    from starlette.testclient import TestClient

    clear_schema_cache()
    repo = ArtifactRepository(shared_artifact_index([engagement_root]))
    gui_state.init_state(repo, engagement_root, None)
    app = FastAPI()
    app.include_router(entities_router)
    return TestClient(app)


class TestEntitySchemataEndpoint:
    def test_base_schema_without_specialization(self, client, engagement_root: Path) -> None:
        _write_schema(
            engagement_root,
            "attributes.collaboration.schema.json",
            {"properties": {"scope": {"type": "string"}}, "required": ["scope"]},
        )
        resp = client.get("/api/entity-schemata", params={"artifact_type": "collaboration"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["properties"] == ["scope"]
        assert body["required"] == ["scope"]
        assert body["specialization"] == ""
        assert body["conflicts"] == []

    def test_specialization_attachment_merges_into_effective_schema(
        self, client, engagement_root: Path
    ) -> None:
        _write_schema(
            engagement_root,
            "attributes.collaboration.schema.json",
            {"properties": {"scope": {"type": "string"}}},
        )
        _write_schema(
            engagement_root,
            "attributes.collaboration.business-collaboration.schema.json",
            {"properties": {"cadence": {"type": "string", "enum": ["weekly", "monthly"]}}, "required": ["cadence"]},
        )
        resp = client.get(
            "/api/entity-schemata",
            params={"artifact_type": "collaboration", "specialization": "business-collaboration"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["properties"]) == {"scope", "cadence"}
        assert body["required"] == ["cadence"]
        assert body["descriptors"]["cadence"]["enum"] == ["weekly", "monthly"]
        assert body["specialization"] == "business-collaboration"

    def test_specialization_absent_from_schema_when_not_selected(
        self, client, engagement_root: Path
    ) -> None:
        _write_schema(
            engagement_root,
            "attributes.collaboration.schema.json",
            {"properties": {"scope": {"type": "string"}}},
        )
        _write_schema(
            engagement_root,
            "attributes.collaboration.business-collaboration.schema.json",
            {"properties": {"cadence": {"type": "string"}}},
        )
        resp = client.get("/api/entity-schemata", params={"artifact_type": "collaboration"})
        body = resp.json()
        assert body["properties"] == ["scope"]

    def test_no_schema_at_all_is_free_schema(self, client) -> None:
        resp = client.get("/api/entity-schemata", params={"artifact_type": "requirement"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["schema"] is None
        assert body["properties"] == []
        assert body["descriptors"] == {}

    def test_array_descriptor_carries_the_item_schema(self, client, engagement_root: Path) -> None:
        # WU-Y1: a list-typed attribute exposes its item schema so the GUI can type each
        # element instead of falling back to a free-text JSON box.
        _write_schema(
            engagement_root,
            "attributes.collaboration.schema.json",
            {"properties": {"tags": {"type": "array", "items": {"type": "string", "enum": ["x", "y"]}}}},
        )
        body = client.get("/api/entity-schemata", params={"artifact_type": "collaboration"}).json()
        tags = body["descriptors"]["tags"]
        assert tags["type"] == "array"
        assert tags["items"] == {"type": "string", "enum": ["x", "y"]}

    def test_clean_pair_is_not_quarantined(self, client, engagement_root: Path) -> None:
        _write_schema(
            engagement_root, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}}
        )
        body = client.get("/api/entity-schemata", params={"artifact_type": "collaboration"}).json()
        assert body["conflicts"] == []
        assert body["quarantined"] is False

    def test_conflicting_attachment_marks_the_pair_quarantined(self, client, engagement_root: Path) -> None:
        # WU-S1: a base↔specialization type conflict surfaces as quarantined on the SAME
        # conflicts channel — the flag the GUI banner + disabled submit read (WU-S2).
        _write_schema(
            engagement_root, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}}
        )
        _write_schema(
            engagement_root,
            "attributes.collaboration.business-collaboration.schema.json",
            {"properties": {"scope": {"type": "integer"}}},
        )
        body = client.get(
            "/api/entity-schemata",
            params={"artifact_type": "collaboration", "specialization": "business-collaboration"},
        ).json()
        assert body["quarantined"] is True
        assert any("scope" in message for message in body["conflicts"])


class TestQuarantineHoldsWithoutTheFlag:
    """The banner and disabled submit are progressive enhancement (WU-S2): a client that
    never reads ``quarantined`` still cannot write ambiguous data, because the single write
    boundary refuses it regardless (PLAN §3 P8)."""

    def _conflicting_pair(self, engagement_root: Path) -> None:
        _write_schema(
            engagement_root, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}}
        )
        _write_schema(
            engagement_root,
            "attributes.collaboration.business-collaboration.schema.json",
            {"properties": {"scope": {"type": "integer"}}},
        )
        clear_schema_cache()

    def test_create_onto_a_quarantined_pair_is_refused_over_rest(self, client, engagement_root: Path) -> None:
        self._conflicting_pair(engagement_root)
        resp = client.post(
            "/api/entity",
            json={
                "artifact_type": "collaboration",
                "name": "Unaware Client Collaboration",
                "specialization": "business-collaboration",
                "dry_run": False,
            },
        )
        assert resp.status_code == 400
        assert "scope" in resp.json()["detail"]
        assert not list(engagement_root.rglob("*collaboration*.md"))

    def test_the_clean_pair_still_writes(self, client, engagement_root: Path) -> None:
        # Guards against the gate over-reaching: quarantine is per (type, specialization).
        _write_schema(
            engagement_root, "attributes.collaboration.schema.json", {"properties": {"scope": {"type": "string"}}}
        )
        clear_schema_cache()
        resp = client.post(
            "/api/entity",
            json={"artifact_type": "collaboration", "name": "Clean Collaboration", "dry_run": False},
        )
        assert resp.status_code == 200
        assert resp.json()["wrote"] is True
