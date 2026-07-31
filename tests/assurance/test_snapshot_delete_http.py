"""The snapshot-deletion REST surface over a REAL SQLCipher store: the capability
gate (423 locked / 403 non-transactional), the outcome→status mapping, the
exactly-one-selector rule, and cross-surface parity with the MCP tool.

Deletion is destructive, so the gate tests assert that a denied call deletes
NOTHING — a denial that had already removed rows would be worse than no gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_CTX_PATH = "src.infrastructure.gui.routers._assurance_signals_routes.get_assurance_context"
def _snapshot_route(snapshot_id: str) -> str:
    return f"/api/assurance/security-snapshots/{snapshot_id}"


def _anchor_route(anchor_entity_id: str) -> str:
    return f"/api/assurance/arch-artifacts/{anchor_entity_id}/security-snapshots"


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

    db_path = tmp_path / "delete.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _RealContext(store, SQLCipherSnapshotStore(store._thread_conn_or_none))  # noqa: SLF001
    store.lock()


def _client(ctx: Any) -> TestClient:
    from src.infrastructure.gui.routers._assurance_signal_deletion_routes import (
        signal_deletion_router,
    )

    client = TestClient(build_api_app(signal_deletion_router), raise_server_exceptions=False)
    client._patch = patch(_CTX_PATH, return_value=ctx)  # type: ignore[attr-defined]
    client._patch.start()  # type: ignore[attr-defined]
    return client


def _activated(ctx: Any, snapshot_id: str, *, anchor: str, request_id: str) -> None:
    store = ctx.snapshot_store
    store.create_staging_snapshot(
        snapshot_id=snapshot_id, anchor_entity_id=anchor, request_id=request_id,
        request_payload_digest=f"d-{request_id}",
    )
    store.populate_snapshot(
        snapshot_id,
        components=[{"component_id": "C1", "name": "urllib3", "purl": "pkg:pypi/urllib3@1"}],
        findings=[{"component_id": "C1", "external_ids": ["CVE-2026-1"]}],
    )
    store.complete_snapshot(snapshot_id)
    store.activate_snapshot(snapshot_id)


class TestScopeIsTheAddress:
    """The scope of a destructive call is the URL, so there is no selector left to get wrong.

    A body that chose between "this snapshot" and "every snapshot of this anchor" made the address
    say nothing about what would be destroyed, and left a third case — neither, or both — that had
    to be refused at runtime. Two routes cannot express it.
    """

    def test_a_body_cannot_widen_the_scope_of_a_snapshot_deletion(self, ctx: Any) -> None:
        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        _activated(ctx, "SNAP@2", anchor="APP@1.aaa", request_id="r2")

        _client(ctx).request(
            "DELETE", _snapshot_route("SNAP@1"), json={"anchor_entity_id": "APP@1.aaa"},
        )

        assert ctx.snapshot_store.get_snapshot("SNAP@2") is not None


class TestOutcomes:
    def test_deleting_one_snapshot_reports_what_it_removed(self, ctx: Any) -> None:
        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")

        resp = _client(ctx).delete(_snapshot_route("SNAP@1"))

        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "no-store"
        payload = resp.json()
        assert payload["status"] == "deleted"
        assert payload["deleted_count"] == 1
        assert payload["deleted"][0]["was_active"] is True
        assert ctx.snapshot_store.get_snapshot("SNAP@1") is None

    def test_deleting_every_snapshot_for_an_anchor(self, ctx: Any) -> None:
        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        _activated(ctx, "SNAP@2", anchor="APP@1.aaa", request_id="r2")

        resp = _client(ctx).delete(_anchor_route("APP@1.aaa"))

        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 2
        assert ctx.snapshot_store.list_snapshots(anchor_entity_id="APP@1.aaa") == []

    def test_unknown_snapshot_is_404_not_a_silent_success(self, ctx: Any) -> None:
        resp = _client(ctx).delete(_snapshot_route("SNAP@nope"))

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"

    def test_anchor_with_no_snapshots_is_404(self, ctx: Any) -> None:
        resp = _client(ctx).delete(_anchor_route("APP@absent.zzz"))

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"


class TestCapabilityGate:
    def test_locked_store_deletes_nothing(self, ctx: Any) -> None:
        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        client = _client(ctx)
        ctx.store.lock()

        resp = client.delete(_snapshot_route("SNAP@1"))

        assert resp.status_code == 423
        ctx.store.unlock()
        assert ctx.snapshot_store.get_snapshot("SNAP@1") is not None

    def test_non_transactional_configuration_deletes_nothing(
        self, ctx: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import src.infrastructure.assurance.signal_gate as gate

        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        monkeypatch.setattr(gate, "storage_assurance_archive_backend", lambda: "s3-worm")

        resp = _client(ctx).delete(_snapshot_route("SNAP@1"))

        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "signal_mutation_denied"
        assert ctx.snapshot_store.get_snapshot("SNAP@1") is not None


class TestCrossSurfaceParity:
    def test_rest_and_mcp_return_the_same_body_for_the_same_delete(
        self, ctx: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """REST and MCP are sibling adapters on one backend, not a caller/callee
        chain, so parity can only be enforced by test."""
        from mcp.server.fastmcp import FastMCP

        from src.infrastructure.mcp.assurance_mcp import security_write_tools

        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        rest = _client(ctx).delete(_snapshot_route("SNAP@1")).json()

        _activated(ctx, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        monkeypatch.setattr(security_write_tools, "get_assurance_context", lambda: ctx)
        server = FastMCP("test-assurance-write")
        security_write_tools.register_security_write_tools(server)
        tool = server._tool_manager._tools["assurance_delete_security_snapshot"].fn  # noqa: SLF001
        mcp = tool(snapshot_id="SNAP@1")

        assert rest == mcp
