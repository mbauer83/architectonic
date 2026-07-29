"""Tests for CAST/GRC verifier rules: E505, W504, W505."""

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


def test_e505_incident_without_investigates(store) -> None:  # type: ignore[no-untyped-def]
    """E505: incident with no investigates edge must be a hard error."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("incident", "INC-1: system crash", concern_class="safety")
    result = verify_store(store)
    codes = [i.code for i in result.errors]
    assert "E505" in codes
    assert not result.valid


def test_e505_incident_with_investigates_passes(store) -> None:  # type: ignore[no-untyped-def]
    """E505: satisfied when incident has at least one investigates edge."""
    from src.application.verification.assurance_verifier import verify_store

    inc_id = store.create_node("incident", "INC-1", concern_class="safety")
    haz_id = store.create_node("hazard", "HAZ-1", concern_class="safety")
    store.add_edge(inc_id, haz_id, "investigates")
    result = verify_store(store)
    codes = [i.code for i in result.errors]
    assert "E505" not in codes


def test_w504_obligation_without_constraint(store) -> None:  # type: ignore[no-untyped-def]
    """W504: obligation with no complies-with constraint emits a warning."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("obligation", "OBL-1: ISO 26262:6-8")
    result = verify_store(store)
    w_codes = [i.code for i in result.warnings]
    assert "W504" in w_codes
    assert result.valid  # warnings don't block


def test_w504_obligation_with_constraint_passes(store) -> None:  # type: ignore[no-untyped-def]
    """W504: obligation with a complies-with constraint has no W504."""
    from src.application.verification.assurance_verifier import verify_store

    obl_id = store.create_node("obligation", "OBL-1")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(acn_id, obl_id, "complies-with")
    result = verify_store(store)
    w_codes = [i.code for i in result.warnings]
    assert "W504" not in w_codes


def test_w505_risk_without_treatment(store) -> None:  # type: ignore[no-untyped-def]
    """W505: risk with no treatment attribute emits a warning."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("risk", "RSK-1: data exposure")
    result = verify_store(store)
    w_codes = [i.code for i in result.warnings]
    assert "W505" in w_codes
    assert result.valid


def test_w505_risk_with_treatment_passes(store) -> None:  # type: ignore[no-untyped-def]
    """W505: risk with treatment attribute set has no W505."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("risk", "RSK-1", attributes={"treatment": "mitigate"})
    result = verify_store(store)
    w_codes = [i.code for i in result.warnings]
    assert "W505" not in w_codes


def test_multiple_new_rules_coexist(store) -> None:  # type: ignore[no-untyped-def]
    """All new CAST/GRC verifier rules can fire independently on the same store."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("incident", "INC-orphan", concern_class="safety")
    store.create_node("obligation", "OBL-orphan")
    store.create_node("risk", "RSK-no-treatment")
    result = verify_store(store)
    error_codes = [i.code for i in result.errors]
    warning_codes = [i.code for i in result.warnings]
    assert "E505" in error_codes
    assert "W504" in warning_codes
    assert "W505" in warning_codes


def test_pre_existing_rules_unaffected(store) -> None:  # type: ignore[no-untyped-def]
    """CAST/GRC additions do not regress existing verifier rules."""
    from src.application.verification.assurance_verifier import verify_store

    store.create_node("unsafe-control-action", "UCA-1", uca_type="not-provided", concern_class="safety")
    store.create_node("assurance-constraint", "ACN-bad", concern_class="safety", disposition="accepted")
    result = verify_store(store)
    error_codes = [i.code for i in result.errors]
    assert "E501" in error_codes
    assert "E503" in error_codes
