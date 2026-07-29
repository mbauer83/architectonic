"""Unit tests for the draft_gsn_from_store logic."""

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


def test_empty_store_returns_generic_top_goal(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    result = draft_gsn_from_store(store)
    assert result["top_goal"]["node_id"] == "G-TOP"
    assert "safe" in str(result["top_goal"]["claim"]).lower() or "secure" in str(result["top_goal"]["claim"]).lower()
    assert result["sub_goals"] == []
    assert result["strategies"] == []
    assert result["solutions"] == []


def test_result_has_required_keys(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    result = draft_gsn_from_store(store)
    assert "top_goal" in result
    assert "sub_goals" in result
    assert "strategies" in result
    assert "solutions" in result
    assert "gaps" in result
    assert "constraints_without_evidence" in result["gaps"]
    assert "hazards_without_constraints" in result["gaps"]


def test_losses_appear_in_top_goal_claim(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    store.create_node("loss", "Loss of vehicle control", concern_class="safety")
    store.create_node("loss", "Data breach", concern_class="security")
    result = draft_gsn_from_store(store)
    claim = str(result["top_goal"]["claim"])
    assert "Loss of vehicle control" in claim
    assert "Data breach" in claim


def test_top_goal_references_losses(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    loss_id = store.create_node("loss", "L-1", concern_class="safety")
    result = draft_gsn_from_store(store)
    assert loss_id in result["top_goal"]["source_losses"]


def test_hazard_creates_sub_goal_and_strategy(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    result = draft_gsn_from_store(store)
    sub_goal_ids = [str(sg["source_hazard"]) for sg in result["sub_goals"]]
    strategy_ids = [str(s["source_hazard"]) for s in result["strategies"]]
    assert haz_id in sub_goal_ids
    assert haz_id in strategy_ids


def test_hazard_sub_goal_references_loss_chain(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    loss_id = store.create_node("loss", "L-1", concern_class="safety")
    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    store.add_edge(haz_id, loss_id, "leads-to")
    result = draft_gsn_from_store(store)
    sub_goal = next(sg for sg in result["sub_goals"] if str(sg["source_hazard"]) == haz_id)
    assert loss_id in sub_goal["leads_to_losses"]


def test_constraint_with_evidence_creates_solution(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    acn_id = store.create_node("assurance-constraint", "Speed limit", concern_class="safety")
    evid_id = store.create_node("evidence", "Test Report T-001")
    store.add_edge(acn_id, evid_id, "evidenced-by")
    result = draft_gsn_from_store(store)
    solution_constraint_ids = [str(s["constraint_id"]) for s in result["solutions"]]
    assert acn_id in solution_constraint_ids


def test_constraint_without_evidence_appears_in_gap(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    acn_id = store.create_node("assurance-constraint", "Brake force", concern_class="safety")
    result = draft_gsn_from_store(store)
    gap_ids = [g["node_id"] for g in result["gaps"]["constraints_without_evidence"]]
    assert acn_id in gap_ids


def test_hazard_without_uca_constraint_appears_in_gap(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    haz_id = store.create_node("hazard", "H-orphan", concern_class="safety")
    result = draft_gsn_from_store(store)
    gap_ids = [g["node_id"] for g in result["gaps"]["hazards_without_constraints"]]
    assert haz_id in gap_ids


def test_hazard_with_full_chain_not_in_gap(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

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
    result = draft_gsn_from_store(store)
    gap_ids = [g["node_id"] for g in result["gaps"]["hazards_without_constraints"]]
    assert haz_id not in gap_ids


def test_strategy_contains_uca_and_constraint_ids(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    haz_id = store.create_node("hazard", "H-1", concern_class="safety")
    ca_id = store.create_node("control-action", "CA-1")
    uca_id = store.create_node(
        "unsafe-control-action", "UCA-1", uca_type="not-provided", concern_class="safety"
    )
    store.add_edge(uca_id, ca_id, "concerns")
    store.add_edge(uca_id, haz_id, "leads-to")
    acn_id = store.create_node("assurance-constraint", "ACN-1", concern_class="safety")
    store.add_edge(uca_id, acn_id, "derives")
    result = draft_gsn_from_store(store)
    strategy = next(s for s in result["strategies"] if str(s["source_hazard"]) == haz_id)
    assert uca_id in strategy["uca_ids"]
    assert acn_id in strategy["constraint_ids"]


def test_gsn_node_types_are_correct(store) -> None:  # type: ignore[no-untyped-def]
    from src.application.verification.case_draft import draft_gsn_from_store

    store.create_node("hazard", "H-1", concern_class="safety")
    result = draft_gsn_from_store(store)
    assert result["top_goal"]["gsn_type"] == "goal"
    for sg in result["sub_goals"]:
        assert sg["gsn_type"] == "goal"
    for s in result["strategies"]:
        assert s["gsn_type"] == "strategy"
    for sn in result["solutions"]:
        assert sn["gsn_type"] == "solution"
