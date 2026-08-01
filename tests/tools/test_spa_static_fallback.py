"""SPA history-fallback static serving: deep links resolve to index.html; assets/api do not."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from src.infrastructure.backend._spa_static import SPAStaticFiles


def _app(dist: Path) -> FastAPI:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body><main>app shell</main></body></html>", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("console.log('app')", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/stats")
    def stats() -> dict[str, int]:
        return {"n": 1}

    app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="static")
    return app


def test_root_serves_index(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<main>" in resp.text


def test_deep_link_falls_back_to_index(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    for route in ("/entities", "/entities/groups", "/documents", "/assurance/analyses"):
        resp = client.get(route)
        assert resp.status_code == 200, route
        assert "<main>" in resp.text, route


def test_real_asset_is_served_not_index(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    resp = client.get("/assets/index-abc.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_missing_asset_still_404s(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    # A missing file with an extension must not be masked by index.html.
    assert client.get("/assets/missing.js").status_code == 404


def test_artifact_deep_links_fall_back_to_index(tmp_path: Path) -> None:
    """A route ending in an artifact id has to boot the SPA.

    Every artifact id contains dots, and the guard against masking a missing bundle used to be
    "the last segment contains a dot" — so every one of these 404ed. The symptom reached a reader
    as an error page after clicking a cross-document citation, and would equally have hit a reload
    or a bookmark of any detail route.
    """
    client = TestClient(_app(tmp_path))
    routes = (
        "/documents/ADR@1780761591._mseZr.adopt-archimate-next-ontology",
        "/documents/STD@1784345879.nNCIH_.motivation-layer-modeling-conventions",
        "/entities/REQ@1712870400.HR7AGz.support-models-diagrams-documents",
        "/entities/REQ@1712870400.HR7AGz.support-models-diagrams-documents/graph",
        "/diagrams/CC@1780829796.SOoZQh.assurance-module-components/edit",
        "/assurance/nodes/CSN@1785236941.pr5f.b33677",
    )
    for route in routes:
        resp = client.get(route)
        assert resp.status_code == 200, route
        assert "<main>" in resp.text, route


def test_missing_files_named_by_every_asset_suffix_still_404(tmp_path: Path) -> None:
    """The closed suffix set is the whole guard now, so each entry must actually deny fallback.

    Asserted over the set itself rather than a sample: an entry that stopped denying would
    otherwise be found by a browser receiving HTML where it asked for a stylesheet.
    """
    from src.infrastructure.backend._spa_static import ASSET_SUFFIXES

    client = TestClient(_app(tmp_path))
    for suffix in sorted(ASSET_SUFFIXES):
        assert client.get(f"/assets/missing.{suffix}").status_code == 404, suffix
        # Case is not part of the name: `MISSING.CSS` is still a stylesheet.
        assert client.get(f"/assets/missing.{suffix.upper()}").status_code == 404, suffix


def test_unknown_api_path_is_not_rewritten(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    # api/ paths must 404 rather than fall back to the SPA shell.
    assert client.get("/api/does-not-exist").status_code == 404
