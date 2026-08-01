"""Tests for read-only viewpoint execution REST endpoints."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src.application.artifacts.repository import ArtifactRepository
from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionTimeoutError
from src.domain.relationships.relationship_reachability import DerivationLimitError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.domain.viewpoints.viewpoint_criteria import EntityCriteriaGroup
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    StyleRule,
    ViewpointCatalog,
    ViewpointDefinition,
)
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.viewpoints import router as viewpoints_router
from tests.support.api_app import build_api_app

httpx = pytest.importorskip("httpx")

ENT_ID = "APC@1000000041.EntSch.viewpoint-exec-entity"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: application-component
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Test entity for viewpoint execution.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: ApplicationComponent
label: "{name}"
alias: APC_test
```
"""


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-VPX" / "architecture-repository"
    _write(root / "model" / "application" / "application-component" / f"{ENT_ID}.md", _entity_md(ENT_ID, "Exec Entity"))
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def client(populated_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.rest.routers.viewpoints import fresh_viewpoints_runtime_catalogs_dependency

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    catalogs = build_runtime_catalogs(get_module_registry())
    definition = ViewpointDefinition(
        slug="exec-test", version=1, name="Exec Test", query=ExecutableViewpointQuery(),
        presentation=PresentationSpec(
            representation="exploration",
            styling_rules=(StyleRule(capability="node_color", match_criteria=EntityCriteriaGroup(), value="positive"),),
        ),
    )
    catalogs = dataclasses.replace(catalogs, viewpoints=ViewpointCatalog(entries=(definition,)))

    app = build_api_app(viewpoints_router)
    app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: catalogs
    return TestClient(app)


class TestPresentationOverride:
    """The optional, additive presentation input on the REST execution routes: inline with a
    query, or an ephemeral override with a slug (stored definition never mutated)."""

    def test_execute_accepts_slug_with_presentation_override(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/execute",
            json={"slug": "exec-test",
                  "presentation": {"representation": "table", "columns": [{"label": "Kind", "source": "Category"}]}},
        )
        assert resp.status_code == 200

    def test_execute_accepts_inline_query_with_presentation(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/execute", json={"query": {}, "presentation": {"representation": "exploration"}}
        )
        assert resp.status_code == 200

    def test_execute_rejects_invalid_presentation(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/execute",
            json={"query": {}, "presentation": {"representation": "not-a-real-representation"}},
        )
        assert resp.status_code == 400
        # `bad_request`, not `invalid-presentation`: the envelope's code comes from the status, and
        # the route's own taxonomy does not survive the translation. See
        # `TestTheExecutionTaxonomyDoesNotReachTheClient` at the end of this module.
        assert resp.json()["detail"]["code"] == "bad_request"
        assert "not-a-real-representation" in resp.json()["detail"]["message"]

    def test_export_csv_uses_override_columns_not_saved(self, client) -> None:
        # The saved exec-test presentation is exploration (no columns); an override table
        # presentation's columns must drive the CSV — proving the slug-only lookup was removed.
        resp = client.post(
            "/api/viewpoints/export-csv",
            json={"slug": "exec-test",
                  "presentation": {"representation": "table", "columns": [{"label": "Kind", "source": "Category"}]}},
        )
        assert resp.status_code == 200
        assert "Kind" in resp.text

    def test_execute_projection_accepts_presentation_override(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/execute-projection",
            json={"slug": "exec-test",
                  "presentation": {"representation": "table", "columns": [{"label": "Kind", "source": "Category"}]}},
        )
        assert resp.status_code == 200

    def test_execute_diagram_accepts_inline_query_with_presentation(self, client) -> None:
        resp = client.post(
            "/api/viewpoints/execute-diagram", json={"query": {}, "presentation": {"representation": "diagram"}}
        )
        assert resp.status_code == 200


class TestSlugExecution:
    def test_executes_known_slug(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"slug": "exec-test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "exec-test"
        assert body["version"] == 1
        assert ENT_ID in body["entity_ids"]

    def test_unknown_slug_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"slug": "does-not-exist"})
        assert resp.status_code == 400


class TestAdHocExecution:
    def test_executes_inline_query(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"query": {}})
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] is None
        assert body["version"] is None
        assert ENT_ID in body["entity_ids"]

    def test_executes_parameterized_derived_traversal_query(self, client) -> None:
        response = client.post(
            "/api/viewpoints/execute",
            json={
                "parameters": {"entity_type": "application-component"},
                "query": {
                    "query_schema": 1,
                    "parameters": [{"name": "entity_type", "type": "string"}],
                    "entity_criteria": {
                        "kind": "group",
                        "conjunction": "and",
                        "children": [
                            {
                                "kind": "condition",
                                "attribute": "type",
                                "comparator": "eq",
                                "value": {"from": "parameter", "name": "entity_type"},
                            }
                        ],
                    },
                    "connections": {"enabled": True, "traversal": "derived", "max_hops": 2},
                },
            },
        )
        assert response.status_code == 200
        assert ENT_ID in response.json()["entity_ids"]


class TestRequestShape:
    def test_both_slug_and_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"slug": "exec-test", "query": {}})
        assert resp.status_code == 400

    def test_neither_slug_nor_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={})
        assert resp.status_code == 400

    def test_response_shape_is_stable(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"slug": "exec-test"})
        body = resp.json()
        assert set(body.keys()) == {
            "slug", "version", "query_schema", "repo_scope", "executed_at", "index_generation",
            "entity_ids", "connection_ids", "entities", "connections",
            "total_entity_count", "returned_entity_count", "total_connection_count", "returned_connection_count",
            "truncated", "entity_limit", "matrix_axes", "warnings", "duration_ms", "query_summary",
            "anchor_ids", "target_population", "aggregation", "bound_parameters", "trace_table",
        }
        # An ordinary viewpoint (no trace_patterns) carries a null trace_table — additive + inert.
        assert body["trace_table"] is None
        # The shared MCP/REST content stays unstyled — no style tokens leak in.
        assert all("style" not in entity for entity in body["entities"])


class TestParameters:
    def test_parameter_errors_have_one_payload_shape_on_every_execution_route(self, client) -> None:
        for endpoint in ("execute", "execute-projection", "execute-diagram"):
            response = client.post(f"/api/viewpoints/{endpoint}", json={"slug": "exec-test", "parameters": {"x": 1}})
            assert response.status_code == 400
            # One payload shape on every route — the envelope's, which is what a client receives.
            # The route's `path` ("parameters/x") is dropped in translation; the message it built is
            # what is left to identify the input.
            assert response.json()["detail"] | {"request_id": None} == {
                "code": "bad_request",
                "message": "unknown-parameter: x",
                "details": None,
                "request_id": None,
            }


class TestTypedExecutionErrors:
    @pytest.mark.parametrize(
        ("error", "status", "envelope_code"),
        [
            (BindingCardinalityError("binding 'one' requires one result, got 2"), 400, "bad_request"),
            (DerivationLimitError(1), 400, "bad_request"),
            # 504 is unmapped, so the envelope calls a gateway timeout an internal error.
            (ViewpointExecutionTimeoutError(2, 1), 504, "internal_error"),
        ],
    )
    def test_returns_issue_payload_without_result(
        self, client, monkeypatch, error: Exception, status: int, envelope_code: str
    ) -> None:
        import src.infrastructure.rest.routers.viewpoints as viewpoints_module

        def _raise(*_args: object, **_kwargs: object) -> object:
            raise error

        monkeypatch.setattr(viewpoints_module, "evaluate_viewpoint", _raise)
        response = client.post("/api/viewpoints/execute", json={"slug": "exec-test"})
        assert response.status_code == status
        # The status is preserved; the route's code and `path` are not, so the message is what
        # distinguishes one execution failure from another.
        assert response.json()["detail"]["code"] == envelope_code
        assert str(error) in response.json()["detail"]["message"]
        assert "entity_ids" not in response.json()


class TestExecuteProjection:
    """The GUI-only styled sibling of ``execute``."""

    def test_executes_known_slug_with_style(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-projection", json={"slug": "exec-test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["target"] == "repository"
        item = next(i for i in body["items"] if i["item_id"] == ENT_ID)
        assert item["style"] == {"node_color": "positive"}

    def test_carries_index_generation_for_snapshot_correlation(self, client) -> None:
        """Same provenance contract as /execute — a consumer pairing an execution result
        with its styled projection can verify both saw the same model snapshot."""
        projection = client.post("/api/viewpoints/execute-projection", json={"slug": "exec-test"}).json()
        execution = client.post("/api/viewpoints/execute", json={"slug": "exec-test"}).json()
        assert isinstance(projection["index_generation"], int)
        assert projection["index_generation"] == execution["index_generation"]

    def test_executes_inline_query(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-projection", json={"query": {}})
        assert resp.status_code == 200
        body = resp.json()
        assert body["target"] == "repository"

    def test_unknown_slug_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-projection", json={"slug": "does-not-exist"})
        assert resp.status_code == 400

    def test_both_slug_and_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-projection", json={"slug": "exec-test", "query": {}})
        assert resp.status_code == 400

    def test_neither_slug_nor_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-projection", json={})
        assert resp.status_code == 400


class TestExportCsv:
    def test_export_is_a_csv_attachment_with_provenance(self, client) -> None:
        resp = client.post("/api/viewpoints/export-csv", json={"slug": "exec-test"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert 'attachment; filename="exec-test-gen' in resp.headers["content-disposition"]
        text = resp.text
        assert "# viewpoint: exec-test v1" in text
        assert "# index_generation:" in text
        assert ENT_ID in text

    def test_unknown_slug_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/export-csv", json={"slug": "does-not-exist"})
        assert resp.status_code == 400


class TestExecuteDiagram:
    """The GUI-only unpersisted ArchiMate diagram rendering route."""

    def test_renders_known_slug_to_svg(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-diagram", json={"slug": "exec-test"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"svg", "warnings", "entity_aliases", "signal_banner"}
        # Keyed and null: a plain definition declares no signal source, and "absent" versus
        # "null" would be two spellings of that one state.
        assert body["signal_banner"] is None
        assert body["svg"] is not None
        assert "<svg" in body["svg"]
        assert isinstance(body["warnings"], list)
        # The rendered SVG's node ids are PlantUML aliases normalized from each entity's
        # `display_alias`, never the raw artifact id — the client needs this mapping to
        # resolve SVG elements back to artifact ids for click-to-select.
        aliases = body["entity_aliases"]
        assert aliases, "expected at least one entity in the rendered diagram"
        for artifact_id, alias in aliases.items():
            assert isinstance(artifact_id, str) and artifact_id
            assert isinstance(alias, str) and alias
        # At least one alias must actually appear in the SVG's `data-qualified-name`
        # (`Namespace.Alias` — the frontend's real matching convention, since PlantUML's own
        # `id="entNNNN"` is an unrelated auto-generated sequence, not the declared alias) —
        # proves the mapping is real, not just present.
        # With component-grouped canvases an entity may sit at top level (no namespace
        # prefix), so accept the qualified name with or without a `Namespace.` part —
        # the frontend matcher takes the last dot-segment either way.
        assert any(f".{alias}" in body["svg"] or f'"{alias}"' in body["svg"] for alias in aliases.values())

    def test_renders_inline_query(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-diagram", json={"query": {}})
        assert resp.status_code == 200
        assert "<svg" in resp.json()["svg"]

    def test_oversized_result_gets_a_friendly_refusal_not_a_renderer_error(self, client, monkeypatch) -> None:
        import src.infrastructure.rest.routers.viewpoints as viewpoints_router

        monkeypatch.setattr(viewpoints_router, "viewpoints_diagram_render_max_entities", lambda: 0)
        resp = client.post("/api/viewpoints/execute-diagram", json={"query": {}})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["code"] == "bad_request"
        assert "too large for diagram rendering" in detail["message"]
        assert "exploration or table" in detail["message"]

    def test_unknown_slug_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-diagram", json={"slug": "does-not-exist"})
        assert resp.status_code == 400

    def test_both_slug_and_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-diagram", json={"slug": "exec-test", "query": {}})
        assert resp.status_code == 400

    def test_neither_slug_nor_query_is_400(self, client) -> None:
        resp = client.post("/api/viewpoints/execute-diagram", json={})
        assert resp.status_code == 400

    def test_no_write_queue_or_artifact_file_access(self, client, monkeypatch) -> None:
        """Regression: this endpoint must reach evaluation/rendering only, never the
        write-queue machinery real diagram creation uses."""
        import src.infrastructure.rest.routers.state as state_mod

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("write-queue must never be touched by execute-diagram")

        monkeypatch.setattr(state_mod, "get_write_deps", _boom, raising=True)
        resp = client.post("/api/viewpoints/execute-diagram", json={"slug": "exec-test"})
        assert resp.status_code == 200

    def test_derived_connections_reach_the_renderer(self, client, monkeypatch) -> None:
        """Regression: a derived connection's synthetic id must never be silently dropped
        by diagram-selection resolution — it should reach the renderer as a synthetic,
        renderer-only ConnectionRecord."""
        import src.infrastructure.rest.routers.viewpoints as viewpoints_mod
        from src.application.viewpoints.execution_result import (
            ConnectionItemSummary,
            EntityItemSummary,
            ViewpointExecutionResult,
        )

        other_id = "APC@1000000042.EntSch.viewpoint-exec-other"
        path_key = "SOME@1---OTHER@2@@archimate-serving@fwd"
        derived_id = f"derived::archimate-realization::{path_key}"
        result = ViewpointExecutionResult(
            slug=None, version=None, query_schema=1, repo_scope="both", executed_at="2026-01-01T00:00:00Z",
            index_generation=None, entity_ids=(ENT_ID, other_id), connection_ids=(derived_id,),
            entities=(
                EntityItemSummary(
                    id=ENT_ID, name="Exec Entity", type="application-component", specialization_slugs=(),
                    domain="application", group="uncategorized", membership="primary",
                ),
                EntityItemSummary(
                    id=other_id, name="Other", type="application-component", specialization_slugs=(),
                    domain="application", group="uncategorized", membership="expanded",
                ),
            ),
            connections=(
                ConnectionItemSummary(
                    id=derived_id, type="archimate-realization", source=ENT_ID, target=other_id, certainty="certain",
                    hops=2, via_connection_ids=("c1", "c2"),
                ),
            ),
            total_entity_count=2, returned_entity_count=2, total_connection_count=1, returned_connection_count=1,
            truncated=False, entity_limit=1000, matrix_axes=None, warnings=(), duration_ms=1.0, query_summary="t",
        )
        monkeypatch.setattr(viewpoints_mod, "evaluate_viewpoint", lambda *a, **kw: result)

        from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

        captured: dict[str, list[ConnectionRecord]] = {}

        def _capture(
            name: str,
            entities: list[EntityRecord],
            connections: list[ConnectionRecord],
            *,
            diagram_type: str,
            repo_root: Path,
            label_attribute: str | None = None,
        ) -> str:
            captured["connections"] = connections
            return "@startuml\n@enduml\n"

        import src.infrastructure.rendering.diagram_builder as diagram_builder_mod

        monkeypatch.setattr(diagram_builder_mod, "generate_archimate_puml_body", _capture)
        monkeypatch.setattr(diagram_builder_mod, "render_puml_svg", lambda *a, **kw: ("<svg/>", []))

        resp = client.post("/api/viewpoints/execute-diagram", json={"query": {}})
        assert resp.status_code == 200
        connection_ids = {c.artifact_id for c in captured["connections"]}
        assert derived_id in connection_ids

    def test_slug_definitions_label_attribute_reaches_the_renderer(self, populated_root: Path, monkeypatch) -> None:
        """A definition's saved ``display_options.label_attribute`` must reach the
        renderer when executing by slug — an ad-hoc query has no saved presentation."""
        from starlette.testclient import TestClient

        from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

        repo = ArtifactRepository(shared_artifact_index([populated_root]))
        gui_state.init_state(repo, populated_root, None)
        catalogs = build_runtime_catalogs(get_module_registry())
        definition = ViewpointDefinition(
            slug="labelled", version=1, name="Labelled", query=ExecutableViewpointQuery(),
            presentation=PresentationSpec(representation="diagram", display_options={"label_attribute": "owner"}),
        )
        catalogs = dataclasses.replace(catalogs, viewpoints=ViewpointCatalog(entries=(definition,)))
        app = build_api_app(viewpoints_router)
        from src.infrastructure.rest.routers.viewpoints import fresh_viewpoints_runtime_catalogs_dependency

        app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: catalogs
        labelled_client = TestClient(app)

        captured: dict[str, object] = {}
        import src.infrastructure.rendering.diagram_builder as diagram_builder_mod

        def _capture(*args: object, **kwargs: object) -> str:
            captured["label_attribute"] = kwargs.get("label_attribute")
            return "@startuml\n@enduml\n"

        monkeypatch.setattr(diagram_builder_mod, "generate_archimate_puml_body", _capture)
        monkeypatch.setattr(diagram_builder_mod, "render_puml_svg", lambda *a, **kw: ("<svg/>", []))

        resp = labelled_client.post("/api/viewpoints/execute-diagram", json={"slug": "labelled"})
        assert resp.status_code == 200
        assert captured["label_attribute"] == "owner"

    def test_ad_hoc_query_has_no_label_attribute(self, client, monkeypatch) -> None:
        captured: dict[str, object] = {}
        import src.infrastructure.rendering.diagram_builder as diagram_builder_mod

        def _capture(*args: object, **kwargs: object) -> str:
            captured["label_attribute"] = kwargs.get("label_attribute")
            return "@startuml\n@enduml\n"

        monkeypatch.setattr(diagram_builder_mod, "generate_archimate_puml_body", _capture)
        monkeypatch.setattr(diagram_builder_mod, "render_puml_svg", lambda *a, **kw: ("<svg/>", []))

        resp = client.post("/api/viewpoints/execute-diagram", json={"query": {}})
        assert resp.status_code == 200
        assert captured["label_attribute"] is None


class TestMalformedAdHocQuery:
    """A structurally invalid ad-hoc query is the caller's error, so it answers 400 with the
    parser's own sentence — the same contract an invalid presentation already has.

    The Query model page composes these interactively, so the field the parser names is the
    whole diagnostic. Letting the parser's ValueError escape turns every one of them into an
    opaque 500 with the message stranded in the server log.
    """

    #: One malformed query per route; `max_hops` has a documented floor of 2.
    _BAD_QUERY = {
        "query_schema": 1,
        "entity_criteria": {"kind": "group", "conjunction": "and", "children": []},
        "include_connected": [{"direction": "incoming", "max_hops": 1}],
    }

    @pytest.mark.parametrize("route", [
        "/api/viewpoints/execute",
        "/api/viewpoints/execute-projection",
        "/api/viewpoints/execute-diagram",
        "/api/viewpoints/export-csv",
    ])
    def test_every_query_accepting_route_answers_400(self, client, route: str) -> None:
        resp = client.post(route, json={"query": self._BAD_QUERY})

        assert resp.status_code == 400, f"{route} returned {resp.status_code}"
        detail = resp.json()["detail"]
        assert detail["code"] == "bad_request"
        assert "max_hops" in detail["message"]

    def test_a_well_formed_query_is_unaffected(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"query": {}})

        assert resp.status_code == 200


class TestTheExecutionTaxonomyDoesNotReachTheClient:
    """The viewpoint routes build an error taxonomy no client can see.

    Seven raise sites across `viewpoints.py` and `_viewpoint_request_parsing.py` pass a structured
    detail — `{"code": "invalid-query", "path": "query", "message": …}` and its siblings
    `invalid-presentation`, `unknown-parameter`, `derivation-limit`, `diagram-render-limit`,
    `binding-cardinality-violation`, `execution-timeout`. None of it survives:
    `http_exception_handler` derives the envelope's code from the HTTP *status* by design, keeps the
    message and discards everything else. So a client branching on `code` sees `bad_request` for six
    genuinely different failures, and `path` — which says *which input* to highlight — is gone.

    This module asserted the taxonomy for as long as it mounted its router on a bare `FastAPI()`,
    where FastAPI echoes `detail` verbatim. Building the app the way the product builds it is what
    made the loss visible.

    Asserted rather than described, so the loss is a statement the suite holds rather than a comment
    someone has to find. Making these codes first-class means widening the closed `ErrorCode`
    vocabulary and giving `path` a declared details DTO — a published-contract decision, so it is
    named here and not taken.
    """

    def test_six_distinct_failures_all_answer_the_same_code(self, client) -> None:
        codes = {
            resp.json()["detail"]["code"]
            for resp in (
                client.post("/api/viewpoints/execute", json={"query": {"query_schema": 99}}),
                client.post(
                    "/api/viewpoints/execute",
                    json={"query": {}, "presentation": {"representation": "not-a-real-representation"}},
                ),
                client.post("/api/viewpoints/execute", json={"slug": "exec-test", "parameters": {"x": 1}}),
            )
        }
        assert codes == {"bad_request"}

    def test_the_input_path_the_route_named_is_absent(self, client) -> None:
        resp = client.post("/api/viewpoints/execute", json={"slug": "exec-test", "parameters": {"x": 1}})
        assert resp.status_code == 400
        assert "path" not in resp.json()["detail"]
        assert resp.json()["detail"]["details"] is None
