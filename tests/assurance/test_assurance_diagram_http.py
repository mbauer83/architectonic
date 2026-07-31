"""HTTP tests for the analysis-scoped derived diagrams, and for the baselines endpoint.

Covers:
  - GET /api/assurance/diagrams → one entry per visible analysis per applicable type
  - GET /api/assurance/analyses/{id}/diagrams/{type}/rendered → PUML + (optional) SVG
  - a type the analysis' method does not draw → 404 naming what it does draw
  - an absent or above-ceiling analysis → 404
  - GET /api/assurance/baselines → list (empty or populated)
  - 423 on all of them when the store is locked
  - Cache-Control: no-store on all responses

**Why the routes are analysis-scoped.** A derived diagram belongs to a unit of work: one control
structure per STPA, one matrix per FMEA. Keyed by type alone there is one slot per type for the
whole store, so a second FMEA has nowhere to put its matrix and rendering "the" matrix means
drawing every analysis at once.

The graph a projection draws is the analysis' *working set* — what it authored plus what it
borrowed. That is what lets an FMEA's matrix show the control-structure nodes an STPA identified
without any copy of them existing, so it is asserted here rather than left to the unit tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

httpx = pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from tests.support.api_app import build_api_app  # noqa: E402

# ── Minimal fakes ─────────────────────────────────────────────────────────────

class _FakeStore:
    def __init__(self, *, unlocked: bool = True) -> None:
        self._unlocked = unlocked
        self._nodes: list[dict[str, Any]] = []
        self._edges: list[dict[str, Any]] = []
        self._analyses: list[dict[str, Any]] = []
        self._members: dict[str, list[str]] = {}

    def is_unlocked(self) -> bool:
        return self._unlocked

    def list_nodes(self, *, analysis_id: str | None = None, **_kw: object) -> list[dict[str, Any]]:
        if analysis_id is None:
            return list(self._nodes)
        return [n for n in self._nodes if n.get("analysis_id") == analysis_id]

    def list_edges(self, **_kw: object) -> list[dict[str, Any]]:
        return list(self._edges)

    def search_nodes(self, q: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return []

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return next((n for n in self._nodes if n["node_id"] == node_id), None)

    def list_arch_refs(self, **_kw: object) -> list[dict[str, Any]]:
        return []

    def list_analyses(self, **_kw: object) -> list[dict[str, Any]]:
        return list(self._analyses)

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return next((a for a in self._analyses if a["analysis_id"] == analysis_id), None)

    def list_analysis_members(self, analysis_id: str) -> list[str]:
        return list(self._members.get(analysis_id, []))

    def stats(self) -> dict[str, Any]:
        return {}


class _FakeArchive:
    def __init__(self, baselines: list[dict[str, Any]] | None = None) -> None:
        self._baselines = baselines or []

    def list_baselines(self) -> list[dict[str, Any]]:
        return list(self._baselines)


class _FakeContext:
    def __init__(
        self,
        store: _FakeStore,
        archive: _FakeArchive | None = None,
        *,
        ceiling: str = "TLP:RED",
    ) -> None:
        self._store = store
        self._archive = archive or _FakeArchive()
        self.max_classification = ceiling

    @property
    def store(self) -> _FakeStore:
        return self._store

    @property
    def archive(self) -> _FakeArchive:
        return self._archive

    def is_available(self) -> bool:
        return self._store.is_unlocked()


_READ_CTX = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"
_HTTP_CTX = "src.infrastructure.gui.routers._assurance_http.get_assurance_context"

_STPA_ID = "STPA@1.aaaa.000001"
_FMEA_ID = "FMEA@1.bbbb.000002"


def _make_client(ctx: _FakeContext, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Both context lookups point at ``ctx``; monkeypatch so nothing leaks into the next test."""
    from src.infrastructure.gui.routers.assurance import router

    # `build_api_app`, not a bare `FastAPI()`: without the error contracts installed a raised
    # `ApiError` becomes a 500 and the test asserts a shape no client receives.
    app = build_api_app(router)
    monkeypatch.setattr(_READ_CTX, lambda: ctx)
    monkeypatch.setattr(_HTTP_CTX, lambda: ctx)
    return TestClient(app, raise_server_exceptions=False)


def _stpa_store() -> _FakeStore:
    store = _FakeStore()
    store._analyses = [
        {"analysis_id": _STPA_ID, "name": "Key availability", "method": "STPA", "tlp": "TLP:WHITE"},
    ]
    return store


# ── GET /api/assurance/diagrams ────────────────────────────────────────────────

def test_list_diagrams_offers_each_analysis_its_applicable_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _stpa_store()
    store._analyses.append(
        {"analysis_id": _FMEA_ID, "name": "Credential backend", "method": "FMEA", "tlp": "TLP:WHITE"}
    )
    r = _make_client(_FakeContext(store), monkeypatch).get("/api/assurance/diagrams")

    assert r.status_code == 200
    entries = r.json()["diagrams"]
    by_analysis = {
        analysis_id: {e["diagram_type"] for e in entries if e["analysis_id"] == analysis_id}
        for analysis_id in (_STPA_ID, _FMEA_ID)
    }
    assert {"bowtie", "control-structure", "uca-matrix"} <= by_analysis[_STPA_ID]
    assert by_analysis[_FMEA_ID] == {"fmea-matrix"}
    assert r.headers.get("cache-control") == "no-store"


def test_list_diagrams_titles_each_entry_for_its_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_client(_FakeContext(_stpa_store()), monkeypatch).get("/api/assurance/diagrams")

    assert {e["title"] for e in r.json()["diagrams"]} == {"Key availability"}


def test_list_diagrams_omits_an_above_ceiling_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry names its analysis, so listing one above the ceiling discloses its existence and
    its method."""
    store = _stpa_store()
    store._analyses.append(
        {"analysis_id": "GRC@1.cccc.3", "name": "EMBARGOED", "method": "CAST", "tlp": "TLP:RED"}
    )
    r = _make_client(_FakeContext(store, ceiling="TLP:GREEN"), monkeypatch).get(
        "/api/assurance/diagrams"
    )

    assert {e["analysis_id"] for e in r.json()["diagrams"]} == {_STPA_ID}


def test_list_diagrams_of_an_empty_store_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_client(_FakeContext(_FakeStore()), monkeypatch).get("/api/assurance/diagrams")

    assert r.status_code == 200
    assert r.json()["diagrams"] == []


def test_list_diagrams_locked_returns_423(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_client(_FakeContext(_FakeStore(unlocked=False)), monkeypatch).get(
        "/api/assurance/diagrams"
    )

    assert r.status_code == 423
    assert r.headers.get("cache-control") == "no-store"


# ── GET /api/assurance/analyses/{id}/diagrams/{type}/rendered ──────────────────

def _rendered(client: TestClient, analysis_id: str, diagram_type: str) -> httpx.Response:
    return client.get(f"/api/assurance/analyses/{analysis_id}/diagrams/{diagram_type}/rendered")


def test_rendered_control_structure_returns_puml(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _rendered(_make_client(_FakeContext(_stpa_store()), monkeypatch), _STPA_ID, "control-structure")

    assert r.status_code == 200
    body = r.json()
    assert body["diagram_id"] == f"{_STPA_ID}::control-structure"
    assert body["analysis_id"] == _STPA_ID
    assert "@startuml" in body["puml"]
    assert "@enduml" in body["puml"]
    assert r.headers.get("cache-control") == "no-store"


def test_rendered_uca_matrix_returns_selectable_grid_data(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _stpa_store()
    store._nodes = [
        {"node_id": "CA1", "node_type": "control-action", "name": "Brake",
         "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
        {"node_id": "U1", "node_type": "unsafe-control-action", "name": "Brake omitted",
         "uca_type": "not-provided", "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
        {"node_id": "H1", "node_type": "hazard", "name": "Collision",
         "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
    ]
    store._edges = [
        {"edge_id": "E1", "source_id": "U1", "target_id": "CA1", "conn_type": "concerns"},
    ]
    body = _rendered(_make_client(_FakeContext(store), monkeypatch), _STPA_ID, "uca-matrix").json()

    assert body["puml"] is None
    assert {node["node_id"] for node in body["nodes"]} == {"CA1", "U1"}
    assert [edge["edge_id"] for edge in body["edges"]] == ["E1"]


def test_rendered_bowtie_returns_store_grounded_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _stpa_store()
    store._nodes = [
        {"node_id": "U1", "node_type": "unsafe-control-action", "name": "Omitted",
         "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
        {"node_id": "H1", "node_type": "hazard", "name": "Collision",
         "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
        {"node_id": "L1", "node_type": "loss", "name": "Injury",
         "tlp": "TLP:GREEN", "analysis_id": _STPA_ID},
    ]
    store._edges = [
        {"edge_id": "E1", "source_id": "U1", "target_id": "H1", "conn_type": "violates"},
        {"edge_id": "E2", "source_id": "H1", "target_id": "L1", "conn_type": "leads-to"},
    ]
    body = _rendered(_make_client(_FakeContext(store), monkeypatch), _STPA_ID, "bowtie").json()

    assert {node["node_id"] for node in body["nodes"]} == {"U1", "H1", "L1"}
    assert {edge["edge_id"] for edge in body["edges"]} == {"E1", "E2"}
    assert "<<top-event>>" in body["puml"]


def test_rendered_draws_only_this_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two analyses in one store are two diagrams, not one drawing of everything."""
    store = _stpa_store()
    other = "STPA@1.dddd.000004"
    store._analyses.append(
        {"analysis_id": other, "name": "Other system", "method": "STPA", "tlp": "TLP:WHITE"}
    )
    # Each hazard leads to its own loss: a bowtie draws pathways, so a node on none of them is not
    # part of the diagram — see `bowtie.notation.project_store_graph`.
    store._nodes = [
        {"node_id": "H1", "node_type": "hazard", "name": "Mine",
         "tlp": "TLP:WHITE", "analysis_id": _STPA_ID},
        {"node_id": "L1", "node_type": "loss", "name": "My loss",
         "tlp": "TLP:WHITE", "analysis_id": _STPA_ID},
        {"node_id": "H2", "node_type": "hazard", "name": "Theirs",
         "tlp": "TLP:WHITE", "analysis_id": other},
        {"node_id": "L2", "node_type": "loss", "name": "Their loss",
         "tlp": "TLP:WHITE", "analysis_id": other},
    ]
    store._edges = [
        {"edge_id": "E1", "source_id": "H1", "target_id": "L1", "conn_type": "leads-to"},
        {"edge_id": "E2", "source_id": "H2", "target_id": "L2", "conn_type": "leads-to"},
    ]
    body = _rendered(_make_client(_FakeContext(store), monkeypatch), _STPA_ID, "bowtie").json()

    assert {node["node_id"] for node in body["nodes"]} == {"H1", "L1"}


def test_rendered_includes_borrowed_nodes_and_marks_what_was_authored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the whole arrangement: an FMEA's matrix shows the components an STPA
    identified, with no copy of them anywhere, and the borrowed ones stay visibly borrowed."""
    store = _stpa_store()
    store._analyses.append(
        {"analysis_id": _FMEA_ID, "name": "Credential backend", "method": "FMEA", "tlp": "TLP:WHITE"}
    )
    store._nodes = [
        {"node_id": "H1", "node_type": "hazard", "name": "Key unavailable",
         "tlp": "TLP:WHITE", "analysis_id": _STPA_ID},
        {"node_id": "FMD1", "node_type": "failure-mode", "name": "Answers with a foreign secret",
         "tlp": "TLP:WHITE", "analysis_id": _FMEA_ID},
    ]
    store._edges = [
        {"edge_id": "E1", "source_id": "FMD1", "target_id": "H1", "conn_type": "leads-to"},
    ]
    store._members = {_FMEA_ID: ["H1"]}

    body = _rendered(_make_client(_FakeContext(store), monkeypatch), _FMEA_ID, "fmea-matrix").json()

    assert {node["node_id"] for node in body["nodes"]} == {"FMD1", "H1"}
    assert [edge["edge_id"] for edge in body["edges"]] == ["E1"]
    assert body["authored_node_ids"] == ["FMD1"]


def test_rendered_omits_an_above_ceiling_borrowed_node(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _stpa_store()
    store._analyses.append(
        {"analysis_id": _FMEA_ID, "name": "Credential backend", "method": "FMEA", "tlp": "TLP:WHITE"}
    )
    store._nodes = [
        {"node_id": "H1", "node_type": "hazard", "name": "EMBARGOED",
         "tlp": "TLP:RED", "analysis_id": _STPA_ID},
        {"node_id": "FMD1", "node_type": "failure-mode", "name": "Wrong secret",
         "tlp": "TLP:WHITE", "analysis_id": _FMEA_ID},
    ]
    store._members = {_FMEA_ID: ["H1"]}
    client = _make_client(_FakeContext(store, ceiling="TLP:GREEN"), monkeypatch)

    body = _rendered(client, _FMEA_ID, "fmea-matrix").json()

    assert {node["node_id"] for node in body["nodes"]} == {"FMD1"}


def test_rendered_type_the_method_does_not_draw_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asking an STPA for a failure-mode grid is a mistake worth reporting, not an empty grid."""
    r = _rendered(_make_client(_FakeContext(_stpa_store()), monkeypatch), _STPA_ID, "fmea-matrix")

    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "unknown_diagram_type"
    # `available` stays structured rather than becoming prose in a field error: a client offering the
    # alternatives needs them as data, which is why this code did not fold into `validation_error`.
    assert "control-structure" in detail["details"]["available"]
    assert "fmea-matrix" not in detail["details"]["available"]


def test_rendered_unknown_type_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _rendered(_make_client(_FakeContext(_stpa_store()), monkeypatch), _STPA_ID, "no-such-diagram")

    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "unknown_diagram_type"


def test_rendered_absent_analysis_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _rendered(
        _make_client(_FakeContext(_stpa_store()), monkeypatch), "STPA@nope.0000.0", "bowtie"
    )

    assert r.status_code == 404


def test_rendered_above_ceiling_analysis_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    store._analyses = [
        {"analysis_id": _STPA_ID, "name": "EMBARGOED", "method": "STPA", "tlp": "TLP:RED"},
    ]
    client = _make_client(_FakeContext(store, ceiling="TLP:GREEN"), monkeypatch)

    assert _rendered(client, _STPA_ID, "bowtie").status_code == 404


def test_rendered_locked_returns_423(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(_FakeContext(_FakeStore(unlocked=False)), monkeypatch)

    assert _rendered(client, _STPA_ID, "control-structure").status_code == 423


def test_rendered_control_structure_svg_null_when_no_plantuml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(_FakeContext(_stpa_store()), monkeypatch)
    monkeypatch.setattr(
        "src.infrastructure.rendering.diagram_builder.render_puml_svg",
        lambda *a, **kw: (None, ["plantuml unavailable"]),
        raising=False,
    )
    monkeypatch.setattr(
        "src.infrastructure.gui.routers.state.maybe_engagement_root",
        lambda: Path("/tmp/does-not-matter"),
        raising=False,
    )
    r = _rendered(client, _STPA_ID, "control-structure")

    assert r.status_code == 200
    assert r.json()["svg"] is None


@pytest.mark.parametrize("diagram_type", ["bowtie", "control-structure"])
def test_rendered_passes_diagram_type_as_render_type(
    diagram_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the render call must name the diagram type, not a literal.

    The endpoint once hard-coded "generic" as the render diagram type. "generic"
    is not a registered diagram type, so render_puml_svg raised KeyError, the
    endpoint swallowed it, and every non-matrix assurance diagram silently
    returned svg=None ("Diagram rendering is unavailable"). The render type must
    be the diagram type itself (bowtie / control-structure — both real diagram
    types whose renderers know how to expand the body).
    """
    monkeypatch.setattr(
        "src.infrastructure.gui.routers.state.maybe_engagement_root",
        lambda: Path("/tmp/does-not-matter"),
        raising=False,
    )
    captured: dict[str, object] = {}

    def _capture(puml: str, repo_root: object, render_type: str) -> tuple[str, list[str]]:
        captured["diagram_type"] = render_type
        return "<svg/>", []

    monkeypatch.setattr(
        "src.infrastructure.rendering.diagram_builder.render_puml_svg", _capture, raising=False
    )
    client = _make_client(_FakeContext(_stpa_store()), monkeypatch)

    r = _rendered(client, _STPA_ID, diagram_type)

    assert r.status_code == 200
    assert r.json()["svg"] == "<svg/>"
    assert captured["diagram_type"] == diagram_type
    assert captured["diagram_type"] != "generic"


# ── GET /api/assurance/baselines ──────────────────────────────────────────────

def test_baselines_empty_store(monkeypatch: pytest.MonkeyPatch) -> None:
    r = _make_client(_FakeContext(_FakeStore()), monkeypatch).get("/api/assurance/baselines")

    assert r.status_code == 200
    assert r.json()["baselines"] == []
    assert r.json()["count"] == 0
    assert r.headers.get("cache-control") == "no-store"


def test_baselines_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = {"sealed_at": "2026-06-20T12:00:00Z", "notes": "Before CAST-001", "head_hash": "abc123"}
    ctx = _FakeContext(_FakeStore(), archive=_FakeArchive(baselines=[baseline]))
    r = _make_client(ctx, monkeypatch).get("/api/assurance/baselines")

    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["baselines"][0]["head_hash"] == "abc123"


def test_baselines_locked_returns_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(unlocked=False))
    r = _make_client(ctx, monkeypatch).get("/api/assurance/baselines")

    assert r.status_code == 423
