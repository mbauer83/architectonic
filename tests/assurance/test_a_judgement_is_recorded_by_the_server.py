"""Who recorded an FMEA factor judgement or a VEX assessment is stated by the server, never the client.

Regression: `POST /api/assurance/nodes/{id}/factor-assessments`,
`POST /api/assurance/arch-artifacts/{id}/vex-assessments` and the MCP tool `assurance_set_fmea_factor`
took `author` from the request, so any client could attribute a judgement to anyone. Until there is a
principal, the recorder is the identity the server is configured with — the one that authors its
commits (`src.config.git_identity`).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_FMEA_CTX = "src.infrastructure.rest.routers.assurance._fmea_routes.get_assurance_context"
_SIGNALS_CTX = "src.infrastructure.rest.routers.assurance._signals_routes.get_assurance_context"
_RECORDER = "Configured Analyst <analyst@example.invalid>"


class _Archive:
    def append(self, *_args: object, **_kwargs: object) -> None:
        return None


class _Context:
    def __init__(self, store: Any) -> None:
        from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
        from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore

        self.store = store
        self.archive = _Archive()
        self.snapshot_store = SQLCipherSnapshotStore(store._thread_conn_or_none)  # noqa: SLF001
        self.vex_store = SQLCipherVexAssessmentStore(store._thread_conn_or_none)  # noqa: SLF001
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        return True


@pytest.fixture()
def ctx(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Context]:
    import src.infrastructure.assurance.signal_gate as gate
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from tests.support.assurance_store_template import provision_store

    monkeypatch.setattr(gate, "storage_assurance_store_backend", lambda: "sqlcipher")
    monkeypatch.setattr(gate, "storage_assurance_signals_backend", lambda: "sqlcipher-colocated")
    monkeypatch.setattr(gate, "storage_assurance_archive_backend", lambda: "standard")
    monkeypatch.setenv("ARCH_GIT_AUTHOR_NAME", "Configured Analyst")
    monkeypatch.setenv("ARCH_GIT_AUTHOR_EMAIL", "analyst@example.invalid")
    db_path = tmp_path / "recorder.db"
    provision_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _Context(store)
    store.lock()


@pytest.fixture()
def client(ctx: _Context, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.infrastructure.rest.routers.assurance.router import router

    for target in (_FMEA_CTX, _SIGNALS_CTX):
        monkeypatch.setattr(target, lambda: ctx)
    return TestClient(build_api_app(router), raise_server_exceptions=False)


class TestFactorAssessment:
    @staticmethod
    def _failure_mode(ctx: _Context) -> str:
        analysis = str(ctx.store.create_analysis("Pumps", "FMEA", tlp="TLP:WHITE"))
        return str(ctx.store.create_node("failure-mode", "Seal leaks", analysis_id=analysis))

    @staticmethod
    def _body(**extra: str) -> dict[str, str]:
        return {
            "factor": "occurrence", "value": "possible", "justification": "judged against the facts",
            "basis_digest": "basis-1", **extra,
        }

    def test_a_body_naming_an_author_is_refused(self, ctx: _Context, client: TestClient) -> None:
        node_id = self._failure_mode(ctx)

        response = client.post(f"/api/assurance/nodes/{node_id}/factor-assessments",
                               json=self._body(author="Someone Else"))

        assert response.status_code == 422, response.text
        assert ctx.store.read_fmea_assessments([node_id]) == {}

    def test_the_judgement_is_recorded_by_the_configured_identity(
        self, ctx: _Context, client: TestClient,
    ) -> None:
        node_id = self._failure_mode(ctx)

        response = client.post(f"/api/assurance/nodes/{node_id}/factor-assessments", json=self._body())

        assert response.status_code == 200, response.text
        [recorded] = ctx.store.read_fmea_assessments([node_id])[node_id]
        assert recorded["author"] == _RECORDER


class TestVexAssessment:
    _URL = "/api/assurance/arch-artifacts/APP@1/vex-assessments"

    @staticmethod
    def _body(**extra: str) -> dict[str, str]:
        return {
            "canonical_component_id": "pkg:pypi/a@1", "canonical_vulnerability_id": "VID@x",
            "vex_status": "not_affected", "justification": "code path unused", **extra,
        }

    @staticmethod
    def _revisions(ctx: _Context) -> list[Any]:
        return ctx.vex_store.list_vex_revisions(
            anchor_entity_id="APP@1", canonical_component_id="pkg:pypi/a@1",
            canonical_vulnerability_id="VID@x",
        )

    def test_a_body_naming_an_author_is_refused(self, ctx: _Context, client: TestClient) -> None:
        response = client.post(self._URL, json=self._body(author="Someone Else"))

        assert response.status_code == 422, response.text
        assert self._revisions(ctx) == []

    def test_the_assessment_is_recorded_by_the_configured_identity(
        self, ctx: _Context, client: TestClient,
    ) -> None:
        response = client.post(self._URL, json=self._body())

        assert response.status_code == 200, response.text
        [recorded] = self._revisions(ctx)
        assert recorded["author"] == _RECORDER


def test_the_mcp_factor_tool_takes_no_author(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

    from src.infrastructure.mcp.assurance_mcp import fmea_write_tools

    monkeypatch.setattr(fmea_write_tools, "get_assurance_context", lambda: None)
    server = MCPServer("probe")
    fmea_write_tools.register_fmea_write_tools(server)

    [tool] = server._tool_manager.list_tools()  # noqa: SLF001 - the registration is the subject
    assert "author" not in tool.parameters["properties"]
