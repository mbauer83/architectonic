"""The modification stamp reaches every read surface, and `/api/entities` can order by it.

A "last modified" column is only trustworthy if the whole population is ordered before the
page slice — otherwise page 1 of 10 shows the newest of 50 arbitrary rows and looks like the
newest of 500. These tests pin the field's presence on every surface and the ordering's scope,
both by calling the handlers and by requesting them over HTTP.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import Request

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state

_STAMPS = {
    "REQ@1000000001.OldAAA.oldest-requirement": "2026-01-01T00:00:00Z",
    "REQ@1000000002.MidAAA.middle-requirement": "2026-04-01T00:00:00Z",
    "REQ@1000000003.NewAAA.newest-requirement": "2026-07-24T09:15:00Z",
}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, stamp: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '{stamp}'
---

<!-- §content -->

## {name}

Test entity.
"""


def _diagram_puml(artifact_id: str, stamp: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
name: "Stamped Diagram"
diagram-type: archimate-motivation
version: 0.1.0
status: draft
last-updated: '{stamp}'
---
@startuml
@enduml
"""


def _document_md(artifact_id: str, stamp: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: adr
title: "Stamped Decision"
version: 0.1.0
status: draft
last-updated: '{stamp}'
---

## Context

Body.
"""


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-STAMP" / "architecture-repository"
    for artifact_id, stamp in _STAMPS.items():
        _write(root / "model" / "motivation" / "requirement" / f"{artifact_id}.md",
               _entity_md(artifact_id, artifact_id.split(".")[-1], stamp))
    _write(root / "diagram-catalog" / "diagrams" / "motivation" / "ARC@1000000004.DiaAAA.stamped.puml",
           _diagram_puml("ARC@1000000004.DiaAAA.stamped", "2026-05-05T05:05:05Z"))
    _write(root / "docs" / "adr" / "ADR@1000000005.DocAAA.stamped.md",
           _document_md("ADR@1000000005.DocAAA.stamped", "2026-06-06T06:06:06Z"))
    gui_state.init_state(ArtifactRepository(shared_artifact_index([root])), root, None)
    return root


def _list_entities(**kwargs: object) -> dict:
    from src.infrastructure.gui.routers.entities import list_entities

    return list_entities(request=cast("Request", None), limit=2000, offset=0, **kwargs)  # type: ignore[arg-type]


def _stamp_by_id(items: list[dict]) -> dict[str, str | None]:
    return {row["artifact_id"]: row.get("last_updated") for row in items}


class TestFieldPresence:
    def test_entity_list_rows_carry_the_stamp(self, repo_root: Path) -> None:
        stamps = _stamp_by_id(_list_entities()["items"])
        assert stamps == _STAMPS

    def test_entity_detail_carries_the_stamp(self, repo_root: Path) -> None:
        from src.infrastructure.gui.routers.entities import read_entity

        detail = read_entity(artifact_id="REQ@1000000003.NewAAA.newest-requirement")
        assert detail["last_updated"] == "2026-07-24T09:15:00Z"

    def test_diagram_list_and_detail_carry_the_stamp(self, repo_root: Path) -> None:
        from src.infrastructure.gui.routers.diagrams import list_diagrams

        (row,) = list_diagrams()["items"]
        assert row["last_updated"] == "2026-05-05T05:05:05Z"

        detail = gui_state.get_repo().read_artifact("ARC@1000000004.DiaAAA.stamped", mode="full")
        assert detail is not None
        assert detail["last_updated"] == "2026-05-05T05:05:05Z"

    def test_document_list_and_detail_carry_the_stamp(self, repo_root: Path) -> None:
        from src.infrastructure.gui.routers.documents import list_documents

        (row,) = list_documents(limit=200)["items"]
        assert row["last_updated"] == "2026-06-06T06:06:06Z"

        detail = gui_state.get_repo().read_artifact("ADR@1000000005.DocAAA.stamped", mode="full")
        assert detail is not None
        assert detail["last_updated"] == "2026-06-06T06:06:06Z"

    def test_search_hits_carry_the_stamp(self, repo_root: Path) -> None:
        result = gui_state.get_repo().search_artifacts("requirement", limit=10)
        serialized = [gui_state.search_hit_to_dict(hit) for hit in result.hits]
        assert serialized
        assert all("last_updated" in hit for hit in serialized)

    def test_mcp_summaries_carry_the_stamp(self, repo_root: Path) -> None:
        from dataclasses import asdict

        summaries = gui_state.get_repo().list_artifacts(
            include_entities=True, include_diagrams=True, include_documents=True,
        )
        by_id = {s.artifact_id: asdict(s)["last_updated"] for s in summaries}
        assert by_id["REQ@1000000001.OldAAA.oldest-requirement"] == "2026-01-01T00:00:00Z"
        assert by_id["ARC@1000000004.DiaAAA.stamped"] == "2026-05-05T05:05:05Z"
        assert by_id["ADR@1000000005.DocAAA.stamped"] == "2026-06-06T06:06:06Z"


class TestOrdering:
    def test_ascending_and_descending_round_trip(self, repo_root: Path) -> None:
        ascending = [row["artifact_id"] for row in _list_entities(sort="last_updated", order="asc")["items"]]
        descending = [row["artifact_id"] for row in _list_entities(sort="last_updated", order="desc")["items"]]
        assert ascending == list(_STAMPS)
        assert descending == list(reversed(list(_STAMPS)))

    def test_ordering_spans_the_population_not_the_page(self, repo_root: Path) -> None:
        from src.infrastructure.gui.routers.entities import list_entities

        page = list_entities(request=cast("Request", None), sort="last_updated", order="desc", limit=1, offset=0)
        assert page["total"] == len(_STAMPS)
        assert [row["artifact_id"] for row in page["items"]] == ["REQ@1000000003.NewAAA.newest-requirement"]

    def test_unknown_sort_field_still_returns_the_full_list(self, repo_root: Path) -> None:
        payload = _list_entities(sort="conn_total", order="desc")
        assert {row["artifact_id"] for row in payload["items"]} == set(_STAMPS)

    def test_unstamped_entities_sort_last(self, repo_root: Path) -> None:
        unstamped = "REQ@1000000006.BarAAA.unstamped-requirement"
        _write(
            repo_root / "model" / "motivation" / "requirement" / f"{unstamped}.md",
            "---\nartifact-id: " + unstamped + "\nartifact-type: requirement\nname: Unstamped\n"
            "version: 0.1.0\nstatus: active\n---\n\n<!-- §content -->\n\n## Unstamped\n\nBody.\n",
        )
        gui_state.init_state(ArtifactRepository(shared_artifact_index([repo_root])), repo_root, None)

        for order in ("asc", "desc"):
            rows = _list_entities(sort="last_updated", order=order)["items"]
            assert rows[-1]["artifact_id"] == unstamped


class TestOverHttp:
    """The same ordering, requested the way a browser requests it.

    Calling the handler directly skips FastAPI's query parsing, which is exactly where a
    parameter name or type mismatch would hide — so the ordering is also exercised over the
    real HTTP surface.
    """

    @pytest.fixture()
    def client(self, repo_root: Path):
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from src.infrastructure.app_bootstrap import install_module_registry
        from src.infrastructure.gui.routers.entities import router as entities_router

        app = FastAPI()
        install_module_registry(app)
        app.include_router(entities_router)
        return TestClient(app)

    def test_sort_and_order_round_trip_over_http(self, client) -> None:
        body = client.get("/api/entities", params={"sort": "last_updated", "order": "desc"}).json()
        assert [row["artifact_id"] for row in body["items"]] == list(reversed(list(_STAMPS)))
        assert all(row["last_updated"] for row in body["items"])

    def test_paging_a_sorted_list_over_http(self, client) -> None:
        body = client.get(
            "/api/entities", params={"sort": "last_updated", "order": "asc", "limit": 2, "offset": 0},
        ).json()
        assert body["total"] == len(_STAMPS)
        assert [row["artifact_id"] for row in body["items"]] == list(_STAMPS)[:2]

    def test_unsorted_request_over_http_still_carries_the_stamp(self, client) -> None:
        body = client.get("/api/entities").json()
        assert {row["artifact_id"]: row["last_updated"] for row in body["items"]} == _STAMPS
