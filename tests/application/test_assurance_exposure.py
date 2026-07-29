"""Unit tests for AssuranceExposurePolicy — pure policy logic, no IO."""

from __future__ import annotations

from src.application.assurance_exposure import (
    AssuranceExposurePolicy,
    Locked,
    NotFound,
    Visible,
    is_above_ceiling,
)

# ── is_above_ceiling ──────────────────────────────────────────────────────────

def test_tlp_ordering_basic() -> None:
    assert not is_above_ceiling("TLP:WHITE", "TLP:RED")
    assert not is_above_ceiling("TLP:GREEN", "TLP:AMBER")
    assert is_above_ceiling("TLP:AMBER", "TLP:GREEN")
    assert is_above_ceiling("TLP:RED", "TLP:AMBER")


def test_same_tlp_not_above() -> None:
    for tlp in ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED"):
        assert not is_above_ceiling(tlp, tlp)


# ── check_locked ──────────────────────────────────────────────────────────────

def test_check_locked_when_not_unlocked() -> None:
    pol = AssuranceExposurePolicy("TLP:RED", False)
    assert isinstance(pol.check_locked(), Locked)


def test_check_locked_returns_none_when_unlocked() -> None:
    pol = AssuranceExposurePolicy("TLP:RED", True)
    assert pol.check_locked() is None


# ── scope ─────────────────────────────────────────────────────────────────────

def test_scope_red_ceiling_not_limited() -> None:
    scope = AssuranceExposurePolicy("TLP:RED", True).scope()
    assert scope.ceiling == "TLP:RED"
    assert not scope.visibility_limited


def test_scope_green_ceiling_is_limited() -> None:
    scope = AssuranceExposurePolicy("TLP:GREEN", True).scope()
    assert scope.visibility_limited


# ── filter_nodes ──────────────────────────────────────────────────────────────

_NODES = [
    {"node_id": "N1", "node_type": "loss", "tlp": "TLP:WHITE", "name": "Safe Loss"},
    {"node_id": "N2", "node_type": "hazard", "tlp": "TLP:AMBER", "name": "Secret Hazard"},
    {"node_id": "N3", "node_type": "risk", "tlp": "TLP:RED", "name": "Top Secret Risk"},
]


def test_filter_nodes_red_ceiling_returns_all() -> None:
    pol = AssuranceExposurePolicy("TLP:RED", True)
    visible, withheld = pol.filter_nodes(_NODES)
    assert len(visible) == 3
    assert withheld == 0


def test_filter_nodes_amber_ceiling_withholds_red() -> None:
    pol = AssuranceExposurePolicy("TLP:AMBER", True)
    visible, withheld = pol.filter_nodes(_NODES)
    assert withheld == 1
    assert all(n["node_id"] != "N3" for n in visible)


def test_filter_nodes_green_ceiling_withholds_amber_and_red() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    visible, withheld = pol.filter_nodes(_NODES)
    assert withheld == 2
    assert len(visible) == 1
    assert visible[0]["node_id"] == "N1"


def test_filter_nodes_secret_names_absent() -> None:
    """Classified names must not appear in visible output."""
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    visible, _ = pol.filter_nodes(_NODES)
    names = {n["name"] for n in visible}
    assert "Secret Hazard" not in names
    assert "Top Secret Risk" not in names


# ── filter_edges ──────────────────────────────────────────────────────────────

_EDGES = [
    {"edge_id": "E1", "source_id": "N1", "target_id": "N2", "conn_type": "leads-to"},
    {"edge_id": "E2", "source_id": "N1", "target_id": "N3", "conn_type": "leads-to"},
    {"edge_id": "E3", "source_id": "N2", "target_id": "N3", "conn_type": "leads-to"},
]


def test_filter_edges_both_endpoints_visible() -> None:
    pol = AssuranceExposurePolicy("TLP:RED", True)
    visible = pol.filter_edges(_EDGES, frozenset({"N1", "N2", "N3"}))
    assert len(visible) == 3


def test_filter_edges_hidden_endpoint_removes_edge() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    visible_ids = frozenset({"N1"})  # N2, N3 hidden
    visible = pol.filter_edges(_EDGES, visible_ids)
    assert visible == []  # all edges touch a hidden node


def test_filter_edges_topology_not_leaked() -> None:
    """Hidden node IDs must not appear in any edge returned to caller."""
    pol = AssuranceExposurePolicy("TLP:AMBER", True)
    visible_ids = frozenset({"N1", "N2"})
    visible = pol.filter_edges(_EDGES, visible_ids)
    for edge in visible:
        assert str(edge["source_id"]) in visible_ids
        assert str(edge["target_id"]) in visible_ids


# ── apply_node ────────────────────────────────────────────────────────────────

def test_apply_node_absent_returns_not_found() -> None:
    pol = AssuranceExposurePolicy("TLP:RED", True)
    assert isinstance(pol.apply_node(None), NotFound)


def test_apply_node_above_ceiling_returns_not_found() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    result = pol.apply_node({"node_id": "N2", "tlp": "TLP:AMBER", "name": "Secret"})
    assert isinstance(result, NotFound)


def test_apply_node_within_ceiling_returns_visible() -> None:
    pol = AssuranceExposurePolicy("TLP:AMBER", True)
    result = pol.apply_node({"node_id": "N1", "tlp": "TLP:WHITE", "name": "Safe"})
    assert isinstance(result, Visible)
    assert result.value["name"] == "Safe"


def test_apply_node_above_ceiling_same_as_absent() -> None:
    """absent and above-ceiling must be indistinguishable."""
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    absent_result = pol.apply_node(None)
    secret_result = pol.apply_node({"node_id": "N99", "tlp": "TLP:RED", "name": "Classified"})
    assert type(absent_result) is type(secret_result)


# ── redact_stats ──────────────────────────────────────────────────────────────

def test_redact_stats_uses_visible_counts_only() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    visible, _ = pol.filter_nodes(_NODES)
    stats = pol.redact_stats(visible, _EDGES)
    assert stats["node_count"] == 1
    assert stats["by_type"] == {"loss": 1}


def test_redact_stats_edge_count_excludes_hidden_endpoints() -> None:
    pol = AssuranceExposurePolicy("TLP:AMBER", True)
    visible, _ = pol.filter_nodes(_NODES)  # N1, N2 visible; N3 hidden
    stats = pol.redact_stats(visible, _EDGES)
    # E2 (N1→N3) and E3 (N2→N3) involve N3 (hidden) → excluded
    assert stats["edge_count"] == 1  # only E1 (N1→N2)


# ── redact_findings ───────────────────────────────────────────────────────────

def test_redact_findings_omits_hidden_node_reference() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    visible_ids = frozenset({"N1"})
    findings = [
        {"code": "W501", "node_id": "N1", "message": "ok"},
        {"code": "E100", "node_id": "N2", "message": "secret reference"},
        {"code": "E200", "message": "no node_id, always visible"},
    ]
    result = pol.redact_findings(findings, visible_ids)
    assert len(result) == 2
    messages = [f["message"] for f in result]
    assert "secret reference" not in messages


# ── filter_security_records ───────────────────────────────────────────────────

def test_filter_security_records_defaults_to_amber() -> None:
    pol = AssuranceExposurePolicy("TLP:GREEN", True)
    recs = [
        {"component_id": "C1"},  # no tlp → defaults TLP:AMBER → withheld
        {"component_id": "C2", "tlp": "TLP:WHITE"},
    ]
    visible, withheld = pol.filter_security_records(recs)
    assert withheld == 1
    assert len(visible) == 1
    assert visible[0]["component_id"] == "C2"
