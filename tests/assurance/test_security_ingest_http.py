"""The security-signal ingest REST surface over a REAL SQLCipher store: the
capability gate (423 locked / 403 non-transactional), the outcome→status mapping
(200 activated & replayed, 409 conflict, 422 invalid), and cross-surface parity —
the same ingest through REST and through the MCP tool yields the same body."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

@pytest.fixture(autouse=True)
def _admissible_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat this file's synthetic anchors as real, permitted architecture
    elements.

    The ingest now validates its anchor against the architecture model, which
    these tests deliberately do not stand up. Patching the resolution point keeps
    the transport under test while stating the assumption out loud — a test that
    silently bypassed validation would stop exercising the real path.
    """
    import src.infrastructure.assurance.anchor_reader as anchor_module
    from src.domain.assurance.security_signal_snapshot import AnchorDescriptor

    class _Admissible:
        def describe_anchor(self, entity_id: str) -> AnchorDescriptor:
            return AnchorDescriptor(
                entity_id=entity_id, artifact_type="application-component",
                specialization="service",
            )

    monkeypatch.setattr(anchor_module, "anchor_reader_for", lambda *a, **k: _Admissible())


_CTX_PATH = "src.infrastructure.gui.routers._assurance_signals_routes.get_assurance_context"

_BOM: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "serialNumber": "urn:uuid:rest",
    "version": 1,
    "metadata": {"component": {"bom-ref": "root", "name": "app", "version": "1.0"}},
    "components": [
        {"bom-ref": "urllib3", "name": "urllib3", "version": "1.26.0",
         "purl": "pkg:pypi/urllib3@1.26.0"},
    ],
    "dependencies": [{"ref": "root", "dependsOn": ["urllib3"]}],
}

_ADVISORY: dict[str, Any] = {
    "id": "OSV-URLLIB",
    "affected": [{
        "package": {"purl": "pkg:pypi/urllib3"},
        "ranges": [{"type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "1.26.5"}]}],
    }],
}


class _RealContext:
    def __init__(self, store: Any, snapshot_store: Any) -> None:
        self.store = store
        self.snapshot_store = snapshot_store
        self.vex_store = None
        self.max_classification = "TLP:RED"

    def is_available(self) -> bool:
        return self.store.is_unlocked()

    def locked_response(self) -> dict[str, object]:
        return {"error": "assurance_store_locked"}


@pytest.fixture()
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import src.infrastructure.assurance.signal_gate as gate
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    monkeypatch.setattr(gate, "storage_assurance_store_backend", lambda: "sqlcipher")
    monkeypatch.setattr(gate, "storage_assurance_signals_backend", lambda: "sqlcipher-colocated")
    monkeypatch.setattr(gate, "storage_assurance_archive_backend", lambda: "standard")

    db_path = tmp_path / "ingest.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _RealContext(store, SQLCipherSnapshotStore(store._thread_conn_or_none))  # noqa: SLF001
    store.lock()


def _client(ctx: Any) -> TestClient:
    from src.infrastructure.gui.routers._assurance_signals_routes import signals_router

    client = TestClient(build_api_app(signals_router), raise_server_exceptions=False)
    client._patch = patch(_CTX_PATH, return_value=ctx)  # type: ignore[attr-defined]
    client._patch.start()  # type: ignore[attr-defined]
    return client


def _url(anchor: str) -> str:
    return f"/api/assurance/arch-artifacts/{anchor}/security-snapshots"


def _body(**overrides: Any) -> dict[str, Any]:
    """The body without the anchor: the anchor is the path, and the body may not repeat it."""
    return {"bom": _BOM, **overrides}


class TestIngestOutcomes:
    def test_supplied_bom_and_advisories_activate_a_snapshot(self, ctx: Any) -> None:
        client = _client(ctx)

        resp = client.post(_url("APP@1"),
                           json=_body(vulnerabilities=[_ADVISORY], request_id="r1"))

        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "no-store"
        payload = resp.json()
        assert payload["status"] == "activated"
        assert payload["component_count"] == 2
        assert payload["finding_count"] == 1
        active = ctx.snapshot_store.get_active_snapshot("APP@1")
        assert active["snapshot_id"] == payload["snapshot_id"]

    def test_the_snapshot_is_immediately_readable_through_the_list_surface(
        self, ctx: Any,
    ) -> None:
        client = _client(ctx)
        client.post(_url("APP@1"),
                           json=_body(vulnerabilities=[_ADVISORY], request_id="r1"))

        findings = client.get("/api/assurance/arch-artifacts/APP@1/security-findings").json()

        assert findings["count"] == 1
        assert findings["findings"][0]["component_purl"] == "pkg:pypi/urllib3@1.26.0"
        assert findings["findings"][0]["component_directness"] == "direct"

    def test_replayed_request_id_is_200_and_writes_nothing_new(self, ctx: Any) -> None:
        client = _client(ctx)
        first = client.post(_url("APP@2"),
                           json=_body(request_id="same")).json()

        second = client.post(_url("APP@2"),
                           json=_body(request_id="same"))

        assert second.status_code == 200
        assert second.json()["status"] == "replayed"
        assert second.json()["snapshot_id"] == first["snapshot_id"]

    def test_reused_request_id_with_a_different_payload_is_409(self, ctx: Any) -> None:
        client = _client(ctx)
        client.post(_url("APP@3"),
                           json=_body(vulnerabilities=[_ADVISORY], request_id="dup"))

        conflict = client.post(_url("APP@3"),
                           json=_body(request_id="dup"))

        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "conflict"

    def test_missing_anchor_is_422(self, ctx: Any) -> None:
        """A blank anchor is still a rejection, now in the shared envelope with its field named."""
        client = _client(ctx)

        resp = client.post(_url("%20%20"), json=_body())

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "validation_error"
        assert detail["details"]["field_errors"][0]["field"] == "anchor_entity_id"

    def test_a_second_ingest_supersedes_the_previous_snapshot(self, ctx: Any) -> None:
        client = _client(ctx)
        first = client.post(_url("APP@4"),
                           json=_body(request_id="a")).json()

        second = client.post(_url("APP@4"),
                           json=_body(request_id="b")).json()

        assert second["superseded_snapshot_id"] == first["snapshot_id"]


class TestIngestGating:
    def test_locked_store_is_423_and_writes_nothing(self, ctx: Any) -> None:
        client = _client(ctx)
        ctx.store.lock()
        try:
            resp = client.post(_url("APP@1"),
                           json=_body())
            assert resp.status_code == 423
            assert resp.headers.get("Cache-Control") == "no-store"
        finally:
            ctx.store.unlock()
        assert ctx.snapshot_store.get_active_snapshot("APP@1") is None

    def test_non_transactional_configuration_is_403_and_writes_nothing(
        self, ctx: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import src.infrastructure.assurance.signal_gate as gate

        monkeypatch.setattr(gate, "storage_assurance_archive_backend", lambda: "cloud-worm")
        client = _client(ctx)

        resp = client.post(_url("APP@1"),
                           json=_body())

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "signal_mutation_denied"
        assert detail["details"]["reason_code"] == "archive_has_no_atomic_boundary"
        assert ctx.snapshot_store.get_active_snapshot("APP@1") is None


class TestCrossSurfaceParity:
    """Same ingest, both transports: one command, one projection, one body."""

    def test_rest_and_mcp_agree_on_the_response_body(
        self, ctx: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mcp.server.fastmcp import FastMCP

        from src.infrastructure.mcp.assurance_mcp import security_write_tools

        rest = _client(ctx).post(
            _url("APP@REST"),
            json=_body(vulnerabilities=[_ADVISORY], request_id="p1"),
        ).json()

        monkeypatch.setattr(security_write_tools, "get_assurance_context", lambda: ctx)
        server = FastMCP("parity")
        security_write_tools.register_security_write_tools(server)
        tool = server._tool_manager._tools["assurance_ingest_security_signals"].fn  # noqa: SLF001
        mcp = tool("APP@MCP", _BOM, [_ADVISORY], "p1")

        assert set(rest) == set(mcp)
        assert rest["status"] == mcp["status"] == "activated"
        assert rest["component_count"] == mcp["component_count"]
        assert rest["finding_count"] == mcp["finding_count"]
        assert rest["snapshot_id"] != mcp["snapshot_id"]  # distinct anchors
