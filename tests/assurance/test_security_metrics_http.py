"""Security metrics + VEX REST surface over a REAL SQLCipher store: locked
gating, unavailable-without-colocated-stores, end-to-end ingest→metrics→VEX
suppression→reopen, validation 422, cross-anchor isolation and
superseded-version no-carry-over (F3.3), and no-store semantics."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.application.security_signals.command import IngestBundle, ingest_security_signals
from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

class _AdmissibleAnchors:
    """Every anchor in this test file is admissible.

    Stated explicitly rather than skipped: the command now REQUIRES an anchor
    reader, so a test that wants to exercise ingestion has to say its anchor is a
    real, permitted architecture element.
    """

    def describe_anchor(self, entity_id: str):  # type: ignore[no-untyped-def]
        from src.domain.assurance.security_signal_snapshot import AnchorDescriptor

        return AnchorDescriptor(
            entity_id=entity_id, artifact_type="application-component",
            specialization="service",
        )


_CTX_PATH = "src.infrastructure.rest.routers._assurance_signals_routes.get_assurance_context"
_counter = itertools.count(1)


class _RealContext:
    def __init__(self, store: Any, snapshot_store: Any, vex_store: Any,
                 ceiling: str = "TLP:RED") -> None:
        self.store = store
        self.snapshot_store = snapshot_store
        self.vex_store = vex_store
        self.max_classification = ceiling

    def is_available(self) -> bool:
        return self.store.is_unlocked()


@pytest.fixture()
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import src.infrastructure.assurance.signal_gate as gate
    from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance._vex_assessment_store import SQLCipherVexAssessmentStore
    from src.infrastructure.assurance.lifecycle import init_store

    monkeypatch.setattr(gate, "storage_assurance_store_backend", lambda: "sqlcipher")
    monkeypatch.setattr(gate, "storage_assurance_signals_backend", lambda: "sqlcipher-colocated")
    monkeypatch.setattr(gate, "storage_assurance_archive_backend", lambda: "standard")

    db_path = tmp_path / "metrics.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    yield _RealContext(
        store,
        SQLCipherSnapshotStore(store._thread_conn_or_none),  # noqa: SLF001
        SQLCipherVexAssessmentStore(store._thread_conn_or_none),  # noqa: SLF001
    )
    store.lock()


def _client(ctx: Any) -> TestClient:
    from src.infrastructure.rest.routers._assurance_signals_routes import signals_router

    client = TestClient(build_api_app(signals_router), raise_server_exceptions=False)
    client._patch = patch(_CTX_PATH, return_value=ctx)  # type: ignore[attr-defined]
    client._patch.start()  # type: ignore[attr-defined]
    return client


def _ingest(ctx: Any, anchor: str, *, vuln: str = "CVE-2024-1", purl: str = "pkg:pypi/a@1") -> str:
    result = ingest_security_signals(
        IngestBundle(
            anchor_entity_id=anchor,
            request_id=f"req-{next(_counter)}",
            components=({"component_id": "C1", "name": "a", "purl": purl,
                         "directness": "direct"},),
            findings=({"component_id": "C1", "external_ids": [vuln],
                       "severity_band": "high", "cvss_score": 8.0},),
        ),
        store=ctx.snapshot_store,
        new_snapshot_id=lambda: f"SNAP@{next(_counter)}",
        anchor_reader=_AdmissibleAnchors(),
    )
    return result.snapshot_id  # type: ignore[union-attr]


def _vex_url(anchor: str) -> str:
    return f"/api/assurance/arch-artifacts/{anchor}/vex-assessments"


def _vex_body(purl: str = "pkg:pypi/a@1", vuln_canonical: str = "",
              vex_status: str = "not_affected") -> dict[str, str]:
    """The body without the anchor: the anchor is the path, and the body may not repeat it."""
    return {
        "canonical_component_id": purl,
        "canonical_vulnerability_id": vuln_canonical,
        "vex_status": vex_status,
        "justification": "code path unused",
        "author": "analyst",
    }


class TestGating:
    def test_locked_store_returns_423_with_no_store(self, ctx: Any) -> None:
        client = _client(ctx)
        ctx.store.lock()
        try:
            resp = client.get("/api/assurance/arch-artifacts/APP@1/security-metrics")
            assert resp.status_code == 423
            assert resp.headers.get("Cache-Control") == "no-store"
        finally:
            ctx.store.unlock()

    def test_missing_colocated_stores_yield_unavailable(self, ctx: Any) -> None:
        ctx.snapshot_store = None
        resp = _client(ctx).get("/api/assurance/arch-artifacts/APP@1/security-metrics")
        assert resp.status_code == 200
        assert resp.json()["availability"] == "unavailable"


class TestEndToEnd:
    def test_ingest_then_metrics_then_vex_suppression_then_reopen(self, ctx: Any) -> None:
        snapshot_id = _ingest(ctx, "APP@1")
        client = _client(ctx)
        before = client.get("/api/assurance/arch-artifacts/APP@1/security-metrics").json()
        assert before["basis_snapshot_id"] == snapshot_id
        assert before["distinct_open_vulnerabilities"] == 1
        assert before["max_cvss_score"] == 8.0

        canonical = ctx.snapshot_store.list_snapshot_findings(snapshot_id)[0][
            "canonical_vulnerability_id"]
        recorded = client.post(_vex_url("APP@1"), json=_vex_body(vuln_canonical=canonical))
        assert recorded.status_code == 200
        assert recorded.json()["revision"] == 1

        suppressed = client.get("/api/assurance/arch-artifacts/APP@1/security-metrics").json()
        assert suppressed["distinct_open_vulnerabilities"] == 0
        assert suppressed["suppressed_finding_count"] == 1

        reopened = client.post(_vex_url("APP@1"), json=_vex_body(
            vuln_canonical=canonical, vex_status="affected"))
        assert reopened.json()["revision"] == 2
        after = client.get("/api/assurance/arch-artifacts/APP@1/security-metrics").json()
        assert after["distinct_open_vulnerabilities"] == 1

    def test_vex_never_crosses_anchors_or_component_versions(self, ctx: Any) -> None:
        snapshot_id = _ingest(ctx, "APP@1")
        _ingest(ctx, "APP@2")
        client = _client(ctx)
        canonical = ctx.snapshot_store.list_snapshot_findings(snapshot_id)[0][
            "canonical_vulnerability_id"]
        # Assessment recorded for APP@2 (other anchor) and for a DIFFERENT version.
        client.post(_vex_url("APP@2"), json=_vex_body(vuln_canonical=canonical))
        client.post(_vex_url("APP@1"), json=_vex_body(
            purl="pkg:pypi/a@2", vuln_canonical=canonical))
        metrics = client.get("/api/assurance/arch-artifacts/APP@1/security-metrics").json()
        assert metrics["distinct_open_vulnerabilities"] == 1  # nothing carried over

    def test_invalid_vex_is_a_422_with_field_errors(self, ctx: Any) -> None:
        resp = _client(ctx).post(_vex_url("APP@1"), json={
            "canonical_component_id": "pkg:pypi/a@1",
            "canonical_vulnerability_id": "VID@x",
            "vex_status": "not_affected",
            "justification": "",
            "author": "analyst",
        })
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "invalid_vex_assessment"
        assert any(e["field"] == "justification" for e in detail["details"]["field_errors"])

    def test_vex_revision_listing(self, ctx: Any) -> None:
        client = _client(ctx)
        client.post(_vex_url("APP@1"), json=_vex_body(vuln_canonical="VID@x"))
        client.post(_vex_url("APP@1"), json=_vex_body(
            vuln_canonical="VID@x", vex_status="affected"))
        resp = client.get(
            "/api/assurance/arch-artifacts/APP@1/vex-assessments"
            "?canonical_component_id=pkg:pypi/a@1&canonical_vulnerability_id=VID@x"
        )
        body = resp.json()
        assert body["count"] == 2
        assert [r["revision"] for r in body["revisions"]] == [1, 2]
        assert resp.headers.get("Cache-Control") == "no-store"

class TestCrossSurfaceConsistency:
    def test_rest_payload_equals_the_application_use_case_verbatim(self, ctx: Any) -> None:
        """I-C3 scaffold: the wire adds and loses nothing — REST (and the MCP
        tool, which serializes the same dataclass) must return exactly what
        compute_security_metrics computes for the same snapshot. The C3
        viewpoint provider joins this comparison when it lands."""
        from dataclasses import asdict

        from src.application.assurance.exposure import AssuranceExposurePolicy
        from src.application.security_signals.metrics import compute_security_metrics

        _ingest(ctx, "APP@1")
        rest = _client(ctx).get(
            "/api/assurance/arch-artifacts/APP@1/security-metrics").json()
        direct = asdict(compute_security_metrics(
            "APP@1", snapshot_store=ctx.snapshot_store, vex_store=ctx.vex_store,
            policy=AssuranceExposurePolicy(ctx.max_classification, True),
        ))
        assert rest == direct


class TestSignalListing:
    """The itemized list REST surface over the active snapshot (the functionality the
    legacy list_bom_components/list_vulnerabilities endpoints provided, on the new model)."""

    def test_components_findings_and_stats_over_the_active_snapshot(self, ctx: Any) -> None:
        _ingest(ctx, "APP@1", vuln="CVE-2024-9", purl="pkg:pypi/a@1")
        client = _client(ctx)

        comps = client.get("/api/assurance/arch-artifacts/APP@1/security-components")
        assert comps.status_code == 200
        assert comps.headers.get("Cache-Control") == "no-store"
        assert comps.json()["count"] == 1
        assert comps.json()["components"][0]["purl"] == "pkg:pypi/a@1"

        finds = client.get("/api/assurance/arch-artifacts/APP@1/security-findings")
        assert finds.json()["count"] == 1
        assert finds.json()["findings"][0]["component_purl"] == "pkg:pypi/a@1"
        assert finds.json()["findings"][0]["severity_band"] == "high"

        scoped = client.get(
            "/api/assurance/arch-artifacts/APP@1/security-findings?purl=pkg:pypi/a@1")
        assert scoped.json()["count"] == 1
        empty = client.get(
            "/api/assurance/arch-artifacts/APP@1/security-findings?purl=pkg:pypi/absent@9")
        assert empty.json()["count"] == 0

        stats = client.get("/api/assurance/security-stats").json()
        assert stats["active_snapshots"] == 1
        assert stats["active_snapshot_bom_components"] == 1
        assert stats["active_snapshot_findings"] == 1
        assert stats["assessed_entity_count"] == 1
        assert [e["entity_id"] for e in stats["assessed_entities"]] == ["APP@1"]

    def test_locked_listing_returns_423(self, ctx: Any) -> None:
        client = _client(ctx)
        ctx.store.lock()
        try:
            resp = client.get("/api/assurance/arch-artifacts/APP@1/security-components")
            assert resp.status_code == 423
            assert resp.headers.get("Cache-Control") == "no-store"
        finally:
            ctx.store.unlock()
