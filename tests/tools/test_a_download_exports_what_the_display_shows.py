"""A lensed download and a lensed display render the *same* body.

The reader's architectural decision about the ad-hoc reading lens is that nothing is persisted: the
choice lives for a visit, so the rendered bytes *are* the display. That makes "export what I am looking
at" a property rather than a feature — and a property with a specific way of failing. Two addresses
serve an image of one diagram, and if each assembles the lens for itself the export becomes a second
opinion about the display, agreeing today and drifting on the first change to either.

So this is an HTTP-level test on both routes, capturing what each hands the renderer. A unit test of
the lens cannot see it: `apply_reading_lens` is not the thing that could disagree — the two *callers*
are. The renderer is the only thing stubbed, because the question is what it was given.

It also holds the two refusals that make the lens a reading:

* **A lensed request never serves the file on disk.** That file is the authored diagram, which is
  exactly what a lensed request is not asking for. Serving it would answer a colouring request with an
  uncoloured picture and a 200.
* **A lensless request still does.** The lens must not cost every ordinary view a PlantUML run.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams import _serving
from src.infrastructure.rest.routers.viewpoints._freshness import (
    fresh_viewpoints_runtime_catalogs_dependency,
)
from tests.support.api_app import build_api_app

_ID = "ARC@1.x.lens-fixture"
_BODY = """@startuml lens-fixture
rectangle "Alpha" <<capability>> as CAP_a
@enduml
"""


def _entity() -> EntityRecord:
    return EntityRecord(
        artifact_id="APP@1",
        artifact_type="capability",
        name="Alpha",
        version="0.1.0",
        status="active",
        domain="business",
        subdomain="",
        path=Path("e.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="Alpha",
        display_alias="CAP_a",
        specializations=(),
        attributes={"risk_score": 7},
    )


class _Repo:
    def __init__(self, record: DiagramRecord) -> None:
        self._record = record
        self.repo_roots = ()

    def get_diagram(self, artifact_id: str) -> DiagramRecord | None:
        return self._record if artifact_id == _ID else None

    def get_entity(self, artifact_id: str) -> None:
        return None

    def get_connection(self, artifact_id: str) -> None:
        return None

    def find_connections_for(self, entity_id: str, **kwargs: object) -> list:
        return []


@pytest.fixture
def rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, list[str]]]:
    """A client over both serving routes, capturing every body handed to a renderer."""
    catalog = tmp_path / "diagram-catalog" / "diagrams"
    catalog.mkdir(parents=True)
    source = catalog / f"{_ID}.puml"
    source.write_text(f"---\nartifact_id: {_ID}\n---\n{_BODY}", encoding="utf-8")
    image = tmp_path / "diagram-catalog" / "rendered" / f"{_ID}.svg"
    image.parent.mkdir(parents=True)
    image.write_text("<svg>the authored diagram</svg>", encoding="utf-8")

    record = DiagramRecord(
        artifact_id=_ID,
        name="Lens Fixture",
        version="0.1.0",
        status="active",
        artifact_type="diagram",
        diagram_type="archimate",
        path=source,
        extra={},
    )
    seen: dict[str, list[str]] = {"svg": [], "bytes": []}

    monkeypatch.setattr(s, "maybe_engagement_root", lambda: tmp_path)
    monkeypatch.setattr(s, "get_repo", lambda: _Repo(record))
    monkeypatch.setattr(s, "get_write_deps", lambda catalogs: (tmp_path, object(), object()))
    monkeypatch.setattr(
        "src.application.viewpoints.placed_occurrences.resolve_placed_entities",
        lambda extra, registry: [_entity()],
    )
    monkeypatch.setattr(
        "src.infrastructure.viewpoints_snapshot.configured_registry_snapshot",
        lambda catalogs, roots: RegistrySnapshot(
            known_entity_types=frozenset({"capability"}),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={"risk_score": "integer"},
            connection_attribute_types={},
            entity_attribute_enums={},
            connection_attribute_enums={},
            symmetric_connection_types=frozenset(),
        ),
    )

    def _svg(body: str, root: Path, diagram_type: str | None = None) -> tuple[str, list[str]]:
        seen["svg"].append(body)
        return "<svg>rendered</svg>", []

    def _bytes(body: str, root: Path, fmt: str, diagram_type: str | None) -> tuple[bytes, str, list[str]]:
        seen["bytes"].append(body)
        return b"rendered", "image/png", []

    monkeypatch.setattr("src.infrastructure.rendering.diagram_builder.render_puml_svg", _svg)
    monkeypatch.setattr("src.infrastructure.rendering.puml_runtime.render_puml_bytes", _bytes)

    router = APIRouter()
    router.include_router(_serving.router)
    app = build_api_app(router)
    app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: object()
    with TestClient(app) as client:
        seen["client"] = client  # type: ignore[assignment]
        yield seen


def _get(rendered: dict, path: str, **params: object):
    return rendered["client"].get(path, params=params)  # type: ignore[index]


_LENS = {"colour_by": "risk_score", "print": ["risk_score"]}


class TestTheExportIsTheDisplay:
    def test_both_routes_render_the_same_body(self, rendered: dict) -> None:
        assert _get(rendered, f"/api/diagrams/{_ID}/svg", **_LENS).status_code == 200
        assert _get(rendered, f"/api/diagrams/{_ID}/download", format="png", **_LENS).status_code == 200

        assert rendered["svg"] == rendered["bytes"]

    def test_the_rendered_body_actually_carries_the_lens(self, rendered: dict) -> None:
        """Otherwise the two could agree by both doing nothing."""
        _get(rendered, f"/api/diagrams/{_ID}/svg", **_LENS)

        assert "risk_score: 7" in rendered["svg"][0]
        assert "#back:" in rendered["svg"][0]


class TestWhatEachRequestIsServed:
    def test_a_lensed_display_never_serves_the_image_on_disk(self, rendered: dict) -> None:
        response = _get(rendered, f"/api/diagrams/{_ID}/svg", **_LENS)

        assert response.text == "<svg>rendered</svg>"
        assert len(rendered["svg"]) == 1

    def test_a_lensless_display_serves_the_image_on_disk(self, rendered: dict) -> None:
        """A lens must not cost every ordinary view a PlantUML run."""
        response = _get(rendered, f"/api/diagrams/{_ID}/svg")

        assert response.text == "<svg>the authored diagram</svg>"
        assert rendered["svg"] == []

    def test_a_lensed_download_is_still_an_attachment(self, rendered: dict) -> None:
        response = _get(rendered, f"/api/diagrams/{_ID}/download", format="png", **_LENS)

        assert response.headers["content-disposition"] == f'attachment; filename="{_ID}.png"'
        assert response.headers["content-type"] == "image/png"

    def test_a_lensless_download_serves_the_file_on_disk(self, rendered: dict) -> None:
        response = _get(rendered, f"/api/diagrams/{_ID}/download", format="svg")

        assert response.text == "<svg>the authored diagram</svg>"
        assert rendered["bytes"] == []
