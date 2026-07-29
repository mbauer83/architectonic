"""Unit tests for the §17(B) cast-complete coverage checker."""

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


@pytest.fixture()
def archive(store):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._archive import SQLCipherAssuranceArchive

    return SQLCipherAssuranceArchive(store._thread_conn_or_none)  # noqa: SLF001


def test_empty_store_passes_all_checks(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    result = run_cast_complete(store, archive)
    assert result["passed"] is True
    assert "All CAST coverage checks passed" in str(result["summary"])


def test_result_structure_shape(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    result = run_cast_complete(store, archive)
    assert "passed" in result
    assert "checks" in result
    assert "summary" in result
    assert "baseline_count" in result
    assert "incident_count" in result
    expected_keys = {
        "baseline_exists",
        "incident_has_investigates",
        "corrective_action_derives_constraint",
    }
    assert set(result["checks"].keys()) == expected_keys


def test_g_g_incident_without_baseline_fails(store, archive) -> None:  # type: ignore[no-untyped-def]
    """G-g: incident without sealed baseline fails cast-complete."""
    from src.application.verification.cast_complete import run_cast_complete

    store.create_node("incident", "INC-1: data breach", concern_class="security")
    result = run_cast_complete(store, archive)
    assert result["passed"] is False
    assert result["checks"]["baseline_exists"]["passed"] is False


def test_incident_with_baseline_baseline_check_passes(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    # Append something to audit log first (baseline requires non-empty log)
    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="CAST baseline", analysis_id="INC-1")
    store.create_node("incident", "INC-1: data breach", concern_class="security")
    result = run_cast_complete(store, archive)
    assert result["checks"]["baseline_exists"]["passed"] is True


def test_incident_without_investigates_fails(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="baseline")
    store.create_node("incident", "INC-1", concern_class="safety")
    result = run_cast_complete(store, archive)
    assert result["checks"]["incident_has_investigates"]["passed"] is False
    assert result["checks"]["incident_has_investigates"]["gap_count"] == 1


def test_incident_with_investigates_passes(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="baseline")
    inc_id = store.create_node("incident", "INC-1", concern_class="safety")
    haz_id = store.create_node("hazard", "HAZ-1", concern_class="safety")
    store.add_edge(inc_id, haz_id, "investigates")
    result = run_cast_complete(store, archive)
    assert result["checks"]["incident_has_investigates"]["passed"] is True


def test_corrective_action_without_derives_fails(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="baseline")
    store.create_node("corrective-action", "CRA-1: fix controller")
    result = run_cast_complete(store, archive)
    assert result["checks"]["corrective_action_derives_constraint"]["passed"] is False


def test_corrective_action_with_derives_passes(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="baseline")
    cra_id = store.create_node("corrective-action", "CRA-1")
    acn_id = store.create_node("assurance-constraint", "ACN-CRA-1", concern_class="safety")
    store.add_edge(cra_id, acn_id, "derives")
    result = run_cast_complete(store, archive)
    assert result["checks"]["corrective_action_derives_constraint"]["passed"] is True


def test_analysis_scoping_isolates_baseline_and_nodes(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    # Baseline + a complete chain belong to A@1 only.
    archive.seal_baseline(notes="b", analysis_id="A@1")
    inc = store.create_node("incident", "INC", concern_class="safety", analysis_id="A@1")
    haz = store.create_node("hazard", "HAZ", concern_class="safety", analysis_id="A@1")
    store.add_edge(inc, haz, "investigates")
    cra = store.create_node("corrective-action", "CRA", analysis_id="A@1")
    acn = store.create_node("assurance-constraint", "ACN", concern_class="safety", analysis_id="A@1")
    store.add_edge(cra, acn, "derives")
    # A@2 has an incident but no baseline of its own.
    store.create_node("incident", "INC2", concern_class="safety", analysis_id="A@2")

    scoped1 = run_cast_complete(store, archive, analysis_id="A@1")
    assert scoped1["passed"] is True
    # A@1's baseline must not satisfy A@2's gate.
    scoped2 = run_cast_complete(store, archive, analysis_id="A@2")
    assert scoped2["checks"]["baseline_exists"]["passed"] is False


def test_complete_cast_chain_passes(store, archive) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.cast_complete import run_cast_complete

    archive.append("CREATE", payload={"test": "setup"})
    archive.seal_baseline(notes="CAST baseline", analysis_id="INC-1")
    inc_id = store.create_node("incident", "INC-1", concern_class="safety")
    haz_id = store.create_node("hazard", "HAZ-1", concern_class="safety")
    store.add_edge(inc_id, haz_id, "investigates")
    cra_id = store.create_node("corrective-action", "CRA-1")
    acn_id = store.create_node("assurance-constraint", "ACN-CRA-1", concern_class="safety")
    store.add_edge(cra_id, acn_id, "derives")
    result = run_cast_complete(store, archive)
    assert result["passed"] is True
    assert result["incident_count"] == 1
    assert result["baseline_count"] == 1
