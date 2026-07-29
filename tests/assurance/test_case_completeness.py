"""Unit tests for argument-completeness checker (run_case_completeness)."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    s = SQLCipherAssuranceStore(db_path)
    s.unlock()
    yield s
    s.lock()


def test_empty_store_passes_all_checks(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    result = run_case_completeness(store)
    assert result["passed"] is True
    assert "All argument-completeness checks passed" in str(result["summary"])


def test_result_has_required_structure(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    result = run_case_completeness(store)
    assert "passed" in result
    assert "checks" in result
    assert "summary" in result
    expected_keys = {"constraint_has_evidence", "hazard_has_constraint", "loss_has_hazard"}
    assert set(result["checks"].keys()) == expected_keys
    for _key, check in result["checks"].items():
        assert "passed" in check
        assert "gap_count" in check
        assert "gaps" in check


def test_constraint_without_evidence_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    acn_id = store.create_node("assurance-constraint", "ACN-orphan", concern_class="safety")
    result = run_case_completeness(store)
    assert result["passed"] is False
    check = result["checks"]["constraint_has_evidence"]
    assert check["passed"] is False
    assert check["gap_count"] == 1
    assert any(g["node_id"] == acn_id for g in check["gaps"])


def test_constraint_with_evidence_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    evid_id = store.create_node("evidence", "Test Report")
    store.add_edge(acn_id, evid_id, "evidenced-by")
    result = run_case_completeness(store)
    check = result["checks"]["constraint_has_evidence"]
    assert check["passed"] is True


def test_hazard_without_constraint_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    haz_id = store.create_node("hazard", "H-orphan", concern_class="safety")
    result = run_case_completeness(store)
    assert result["passed"] is False
    check = result["checks"]["hazard_has_constraint"]
    assert check["passed"] is False
    assert any(g["node_id"] == haz_id for g in check["gaps"])


def test_hazard_with_uca_constraint_chain_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    ca_id = store.create_node("control-action", "CA-1")
    uca_id = store.create_node(
        "unsafe-control-action", "UCA-1", uca_type="not-provided", concern_class="safety"
    )
    store.add_edge(uca_id, ca_id, "concerns")
    store.add_edge(uca_id, haz_id, "leads-to")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(uca_id, acn_id, "derives")
    result = run_case_completeness(store)
    check = result["checks"]["hazard_has_constraint"]
    gap_ids = [g["node_id"] for g in check["gaps"]]
    assert haz_id not in gap_ids


def test_hazard_via_loss_scenario_chain_passes(store) -> None:  # type: ignore[no-untyped-def]
    """Hazard covered via loss-scenario→derives chain also passes."""
    from src.application.verification.case_draft import run_case_completeness

    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    ca_id = store.create_node("control-action", "CA-1")
    uca_id = store.create_node(
        "unsafe-control-action", "UCA-1", uca_type="not-provided", concern_class="safety"
    )
    store.add_edge(uca_id, ca_id, "concerns")
    store.add_edge(uca_id, haz_id, "leads-to")
    ls_id = store.create_node("loss-scenario", "LS-1", concern_class="safety")
    store.add_edge(ls_id, uca_id, "explains")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(ls_id, acn_id, "derives")
    result = run_case_completeness(store)
    check = result["checks"]["hazard_has_constraint"]
    gap_ids = [g["node_id"] for g in check["gaps"]]
    assert haz_id not in gap_ids


def test_loss_without_hazard_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    loss_id = store.create_node("loss", "L-orphan", concern_class="safety")
    result = run_case_completeness(store)
    assert result["passed"] is False
    check = result["checks"]["loss_has_hazard"]
    assert check["passed"] is False
    assert any(g["node_id"] == loss_id for g in check["gaps"])


def test_loss_with_hazard_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    loss_id = store.create_node("loss", "L-1", concern_class="safety")
    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    store.add_edge(haz_id, loss_id, "leads-to")
    result = run_case_completeness(store)
    check = result["checks"]["loss_has_hazard"]
    assert check["passed"] is True


def test_complete_chain_all_pass(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    loss_id = store.create_node("loss", "L-1", concern_class="safety")
    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    store.add_edge(haz_id, loss_id, "leads-to")
    ca_id = store.create_node("control-action", "CA-1")
    uca_id = store.create_node(
        "unsafe-control-action", "UCA-1", uca_type="not-provided", concern_class="safety"
    )
    store.add_edge(uca_id, ca_id, "concerns")
    store.add_edge(uca_id, haz_id, "leads-to")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(uca_id, acn_id, "derives")
    evid_id = store.create_node("evidence", "Test Report T-001")
    store.add_edge(acn_id, evid_id, "evidenced-by")
    result = run_case_completeness(store)
    assert result["passed"] is True
    assert "All argument-completeness checks passed" in str(result["summary"])


def test_summary_reports_gap_counts(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    store.create_node("loss", "L-1", concern_class="safety")
    store.create_node("loss", "L-2", concern_class="safety")
    result = run_case_completeness(store)
    assert result["passed"] is False
    assert "2" in str(result["summary"])


def test_multiple_constraints_all_need_evidence(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import run_case_completeness

    acn1 = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    acn2 = store.create_node("assurance-constraint", "ACN-2", concern_class="safety")
    evid = store.create_node("evidence", "Test Report")
    store.add_edge(acn1, evid, "evidenced-by")
    # acn2 has no evidence
    result = run_case_completeness(store)
    check = result["checks"]["constraint_has_evidence"]
    assert check["passed"] is False
    gap_ids = [g["node_id"] for g in check["gaps"]]
    assert acn2 in gap_ids
    assert acn1 not in gap_ids
