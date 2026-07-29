"""Unit tests for the §17(B) grc-control-coverage-complete checker."""

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
    from src.application.verification.grc_complete import run_grc_complete

    result = run_grc_complete(store)
    assert result["passed"] is True
    assert "All GRC coverage checks passed" in str(result["summary"])


def test_result_structure_shape(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    result = run_grc_complete(store)
    assert "passed" in result
    assert "checks" in result
    assert "summary" in result
    expected_keys = {"obligation_has_constraint", "risk_has_treatment", "risk_has_owner"}
    assert set(result["checks"].keys()) == expected_keys


def test_obligation_without_constraint_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    store.create_node("obligation", "OBL-1: ISO26262:6-8", attributes={"scheme": "ISO26262", "code": "6-8"})
    result = run_grc_complete(store)
    assert result["checks"]["obligation_has_constraint"]["passed"] is False
    assert result["checks"]["obligation_has_constraint"]["gap_count"] == 1


def test_obligation_with_constraint_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    obl_id = store.create_node("obligation", "OBL-1")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(acn_id, obl_id, "complies-with")
    result = run_grc_complete(store)
    assert result["checks"]["obligation_has_constraint"]["passed"] is True


def test_risk_without_treatment_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    store.create_node("risk", "RSK-1: data exposure")
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_treatment"]["passed"] is False
    assert result["checks"]["risk_has_treatment"]["gap_count"] == 1


def test_risk_with_treatment_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_treatment"]["passed"] is True


def test_risk_without_owner_fails(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_owner"]["passed"] is False


def test_risk_with_owner_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    risk_id = store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    owner_id = store.create_node("control-structure-node", "Security Officer", node_role="controller")
    store.add_edge(owner_id, risk_id, "accountable-for")
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_owner"]["passed"] is True


def test_complete_grc_chain_passes(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    obl_id = store.create_node("obligation", "OBL-1", attributes={"scheme": "ISO27001", "code": "A.8.1"})
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="security")
    store.add_edge(acn_id, obl_id, "complies-with")
    risk_id = store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate", "likelihood": "low"})
    owner_id = store.create_node("control-structure-node", "CISO", node_role="controller")
    store.add_edge(owner_id, risk_id, "accountable-for")
    result = run_grc_complete(store)
    assert result["passed"] is True


def test_summary_reports_gap_counts(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    store.create_node("obligation", "OBL-1")
    store.create_node("obligation", "OBL-2")
    result = run_grc_complete(store)
    assert "2" in str(result["summary"])
    assert result["passed"] is False


def test_arch_ref_alone_never_satisfies_ownership(store) -> None:  # type: ignore[no-untyped-def]
    """Ownership has exactly ONE representation: the accountable-for edge from an
    organizational controller. A bare architecture reference is not an owner —
    the owner NODE may bind to an architecture role, but the reference cannot
    replace the accountability edge."""
    from src.application.verification.grc_complete import run_grc_complete

    risk_id = store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    store.register_arch_ref(risk_id, "ACT@1712870400.role", "binds-to")
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_owner"]["passed"] is False


def test_unrelated_arch_ref_does_not_satisfy_owner(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    risk_id = store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    store.register_arch_ref(risk_id, "APP@1", "binds-to")
    result = run_grc_complete(store)
    assert result["checks"]["risk_has_owner"]["passed"] is False


def test_analysis_scoping_isolates_other_analyses(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.grc_complete import run_grc_complete

    a1 = store.create_analysis("Q3", "GRC")
    a2 = store.create_analysis("Q4", "GRC")
    # An untreated risk in a2 must not fail a1's coverage.
    store.create_node("risk", "A2-RSK", analysis_id=a2)
    risk_id = store.create_node("risk", "A1-RSK", attributes={"treatment": "mitigate"}, analysis_id=a1)
    owner_id = store.create_node("control-structure-node", "Q3 Risk Owner", node_role="controller", analysis_id=a1)
    store.add_edge(owner_id, risk_id, "accountable-for")
    scoped = run_grc_complete(store, analysis_id=a1)
    assert scoped["passed"] is True
    overall = run_grc_complete(store)
    assert overall["checks"]["risk_has_treatment"]["passed"] is False
