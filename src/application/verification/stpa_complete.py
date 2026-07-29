"""§17(B) STPA basic-complete coverage profile checker.

Checks that the full STPA analysis chain is connected:
  - Every hazard has ≥1 loss via leads-to
  - Every UCA has ≥1 control-action via concerns AND ≥1 hazard via leads-to
  - Every loss-scenario explains ≥1 UCA or ≥1 hazard (the handbook's two
    scenario types: type-a explains why a UCA occurs; type-b explains how a
    correct control action is improperly executed or not executed, producing
    the hazard without an intervening UCA)
  - Every UCA and every loss-scenario has ≥1 constraint via derives
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.application.assurance_ports import ConfidentialAssuranceStore


class _CheckEntry(TypedDict):
    passed: bool
    gap_count: int
    gaps: list[dict[str, str]]


def _gap_nodes(
    nodes: list[dict[str, object]],
    node_type: str,
    edges: list[dict[str, object]],
    *,
    source_conn: str | None,
    target_conn: str | None,
) -> list[dict[str, str]]:
    """Return nodes of *node_type* lacking the required outgoing or incoming edge."""
    gaps: list[dict[str, str]] = []
    for node in nodes:
        if str(node.get("node_type", "")) != node_type:
            continue
        nid = str(node["node_id"])
        if source_conn is not None:
            count = sum(
                1 for e in edges
                if str(e["source_id"]) == nid and str(e["conn_type"]) == source_conn
            )
        elif target_conn is not None:
            count = sum(
                1 for e in edges
                if str(e["target_id"]) == nid and str(e["conn_type"]) == target_conn
            )
        else:
            count = 0
        if count < 1:
            gaps.append({"node_id": nid, "name": str(node.get("name", ""))})
    return gaps


def _check(
    checks: dict[str, _CheckEntry],
    key: str,
    gaps: list[dict[str, str]],
) -> None:
    checks[key] = {
        "passed": len(gaps) == 0,
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def run_stpa_complete(
    store: ConfidentialAssuranceStore,
    *,
    analysis_id: str | None = None,
) -> dict[str, object]:
    """Run all §17(B) stpa-basic-complete checks and return a structured result.

    When ``analysis_id`` is given, only that analysis's nodes (and the edges between
    them) are checked, so the wizard reports completeness for one unit of work.
    """
    all_nodes = store.list_nodes(analysis_id=analysis_id)
    if analysis_id is None:
        all_edges = store.list_edges()
    else:
        scoped = {str(n["node_id"]) for n in all_nodes}
        all_edges = [
            e for e in store.list_edges()
            if str(e.get("source_id")) in scoped and str(e.get("target_id")) in scoped
        ]

    checks: dict[str, _CheckEntry] = {}

    _check(
        checks, "hazard_leads_to_loss",
        _gap_nodes(all_nodes, "hazard", all_edges, source_conn="leads-to", target_conn=None),
    )
    _check(
        checks, "uca_concerns_control_action",
        _gap_nodes(all_nodes, "unsafe-control-action", all_edges, source_conn="concerns", target_conn=None),
    )
    _check(
        checks, "uca_leads_to_hazard",
        _gap_nodes(all_nodes, "unsafe-control-action", all_edges, source_conn="leads-to", target_conn=None),
    )
    _check(
        checks, "loss_scenario_explains_uca_or_hazard",
        _gap_nodes(all_nodes, "loss-scenario", all_edges, source_conn="explains", target_conn=None),
    )
    _check(
        checks, "uca_derives_constraint",
        _gap_nodes(all_nodes, "unsafe-control-action", all_edges, source_conn="derives", target_conn=None),
    )
    _check(
        checks, "loss_scenario_derives_constraint",
        _gap_nodes(all_nodes, "loss-scenario", all_edges, source_conn="derives", target_conn=None),
    )

    all_passed = all(v["passed"] for v in checks.values())
    total_gaps = sum(v["gap_count"] for v in checks.values())
    failed_count = sum(1 for v in checks.values() if not v["passed"])
    summary = (
        "All STPA coverage checks passed."
        if all_passed
        else f"{total_gaps} coverage gap(s) found across {failed_count} check(s)."
    )

    return {"passed": all_passed, "checks": checks, "summary": summary}
