"""Tests for assurance_promotion.py — promotion_preflight.

Covers: safe promotion (no constraints), blocking on missing owner/evidence,
TLP warnings, node_ids filter, non-constraint nodes skipped.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.application.assurance_promotion import promotion_preflight


def _make_store(nodes: list[dict], edges: list[dict] | None = None) -> MagicMock:
    store = MagicMock()
    store.list_nodes = lambda: nodes
    store.list_edges = lambda: edges or []
    return store


class TestPromotionPreflightSafe:
    def test_empty_store_is_safe(self) -> None:
        store = _make_store([])
        result = promotion_preflight(store)
        assert result["promote_safe"] is True
        assert result["blocking_count"] == 0
        assert result["warning_count"] == 0

    def test_non_constraint_node_skipped(self) -> None:
        store = _make_store([
            {"node_id": "1", "node_type": "assurance-argument", "concern_class": "safety"},
        ])
        result = promotion_preflight(store)
        assert result["promote_safe"] is True

    def test_constraint_with_owner_and_evidence_is_safe(self) -> None:
        store = _make_store(
            nodes=[{"node_id": "C1", "node_type": "assurance-constraint", "concern_class": "safety"}],
            edges=[
                {"target_id": "C1", "source_id": "OWNER", "conn_type": "responsible-for"},
                {"source_id": "C1", "target_id": "EV1", "conn_type": "evidenced-by"},
            ],
        )
        result = promotion_preflight(store)
        assert result["promote_safe"] is True
        assert result["blocking_count"] == 0


class TestPromotionPreflightBlocking:
    def test_missing_owner_blocks(self) -> None:
        store = _make_store(
            nodes=[{
                "node_id": "C1", "node_type": "assurance-constraint",
                "concern_class": "safety", "name": "No Owner",
            }],
            edges=[{"source_id": "C1", "target_id": "EV1", "conn_type": "evidenced-by"}],
        )
        result = promotion_preflight(store)
        assert result["promote_safe"] is False
        assert result["blocking_count"] == 1
        assert any(b["issue"] == "missing_owner" for b in result["blocking"])

    def test_missing_evidence_blocks(self) -> None:
        store = _make_store(
            nodes=[{
                "node_id": "C2", "node_type": "assurance-constraint",
                "concern_class": "security", "name": "No Evidence",
            }],
            edges=[{"target_id": "C2", "source_id": "OWNER", "conn_type": "responsible-for"}],
        )
        result = promotion_preflight(store)
        assert result["promote_safe"] is False
        assert any(b["issue"] == "missing_evidence" for b in result["blocking"])

    def test_both_missing_produces_two_blocks(self) -> None:
        store = _make_store(
            nodes=[{
                "node_id": "C3", "node_type": "assurance-constraint",
                "concern_class": "safety", "name": "Both Missing",
            }],
            edges=[],
        )
        result = promotion_preflight(store)
        assert result["blocking_count"] == 2


class TestPromotionPreflightTLP:
    def test_tlp_amber_produces_warning(self) -> None:
        store = _make_store(
            nodes=[{
                "node_id": "C4", "node_type": "assurance-constraint",
                "concern_class": "other", "tlp": "TLP:AMBER", "name": "Amber",
            }],
            edges=[],
        )
        result = promotion_preflight(store)
        assert result["promote_safe"] is True
        assert result["warning_count"] == 1
        assert any(w["tlp"] == "TLP:AMBER" for w in result["warnings"])

    def test_tlp_red_produces_warning(self) -> None:
        store = _make_store(
            nodes=[{"node_id": "C5", "node_type": "assurance-constraint", "concern_class": "other", "tlp": "TLP:RED"}],
            edges=[],
        )
        result = promotion_preflight(store)
        assert result["warning_count"] == 1

    def test_tlp_white_no_warning(self) -> None:
        store = _make_store(
            nodes=[{
                "node_id": "C6", "node_type": "assurance-constraint",
                "concern_class": "other", "tlp": "TLP:WHITE",
            }],
            edges=[],
        )
        result = promotion_preflight(store)
        assert result["warning_count"] == 0


class TestPromotionPreflightNodeIdFilter:
    def test_filters_to_specified_node_ids(self) -> None:
        nodes = [
            {"node_id": "C7", "node_type": "assurance-constraint", "concern_class": "safety", "name": "In filter"},
            {"node_id": "C8", "node_type": "assurance-constraint", "concern_class": "safety", "name": "Not in filter"},
        ]
        store = _make_store(nodes, edges=[])
        result = promotion_preflight(store, node_ids=["C8"])
        blocking_ids = [b["node_id"] for b in result["blocking"]]
        assert "C8" in blocking_ids
        assert "C7" not in blocking_ids

    def test_none_node_ids_checks_all(self) -> None:
        nodes = [
            {"node_id": "C9", "node_type": "assurance-constraint", "concern_class": "safety", "name": "One"},
            {"node_id": "C10", "node_type": "assurance-constraint", "concern_class": "safety", "name": "Two"},
        ]
        store = _make_store(nodes, edges=[])
        result = promotion_preflight(store, node_ids=None)
        assert result["blocking_count"] == 4
