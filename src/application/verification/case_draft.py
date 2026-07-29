"""GSN argument-draft and argument-completeness logic for assurance cases.

Functions:
  draft_gsn_from_store  — build a GSN scaffold dict from store content
  run_case_completeness — check argument completeness (evidence + chain coverage)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.application.assurance_ports import ConfidentialAssuranceStore


class _CheckEntry(TypedDict):
    passed: bool
    gap_count: int
    gaps: list[dict[str, str]]


# ── GSN scaffolding ────────────────────────────────────────────────────────────

def _nodes_of(all_nodes: list[dict[str, object]], node_type: str) -> list[dict[str, object]]:
    return [n for n in all_nodes if str(n.get("node_type", "")) == node_type]


def _edges_of(
    all_edges: list[dict[str, object]],
    source_id: str | None = None,
    target_id: str | None = None,
    conn_type: str | None = None,
) -> list[dict[str, object]]:
    result = all_edges
    if source_id is not None:
        result = [e for e in result if str(e["source_id"]) == source_id]
    if target_id is not None:
        result = [e for e in result if str(e["target_id"]) == target_id]
    if conn_type is not None:
        result = [e for e in result if str(e["conn_type"]) == conn_type]
    return result


def _analysis_graph(
    store: ConfidentialAssuranceStore,
    analysis_id: str | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = store.list_nodes(analysis_id=analysis_id)
    if analysis_id is None:
        return nodes, store.list_edges()
    node_ids = {str(node["node_id"]) for node in nodes}
    edges = [
        edge
        for edge in store.list_edges()
        if str(edge["source_id"]) in node_ids and str(edge["target_id"]) in node_ids
    ]
    return nodes, edges


def draft_gsn_from_store(
    store: ConfidentialAssuranceStore,
    *,
    analysis_id: str | None = None,
) -> dict[str, object]:
    """Build a structured GSN scaffold from an analysis-scoped store graph."""
    return draft_gsn_from_records(*_analysis_graph(store, analysis_id))


def draft_gsn_from_records(
    all_nodes: list[dict[str, object]],
    all_edges: list[dict[str, object]],
) -> dict[str, object]:
    """Build a structured GSN scaffold from store content.

    Returns a dict with:
      top_goal     — overall safety/security claim (from losses)
      sub_goals    — one per hazard, linked to losses
      strategies   — per hazard: "Argument by constraint derivation"
      solutions    — evidence artifacts (from evidenced-by edges on constraints)
      gaps         — constraints without evidence, hazards without constraints
    """
    losses = _nodes_of(all_nodes, "loss")
    hazards = _nodes_of(all_nodes, "hazard")
    constraints = _nodes_of(all_nodes, "assurance-constraint")

    # Top goal: derived from all losses
    if losses:
        loss_names = ", ".join(str(n.get("name", "")) for n in losses)
        top_goal: dict[str, object] = {
            "node_id": "G-TOP",
            "gsn_type": "goal",
            "claim": f"The system prevents: {loss_names}",
            "source_losses": [str(n["node_id"]) for n in losses],
        }
    else:
        top_goal = {
            "node_id": "G-TOP",
            "gsn_type": "goal",
            "claim": "The system is acceptably safe/secure.",
            "source_losses": [],
        }

    # Sub-goals: one per hazard
    sub_goals: list[dict[str, object]] = []
    strategies: list[dict[str, object]] = []

    for hazard in hazards:
        hid = str(hazard["node_id"])
        hname = str(hazard.get("name", hid))

        # Which losses does this hazard lead to?
        leads_to = _edges_of(all_edges, source_id=hid, conn_type="leads-to")
        loss_ids = [str(e["target_id"]) for e in leads_to]

        sub_goal: dict[str, object] = {
            "node_id": f"G-{hid}",
            "gsn_type": "goal",
            "claim": f"Hazard '{hname}' is controlled",
            "source_hazard": hid,
            "leads_to_losses": loss_ids,
        }
        sub_goals.append(sub_goal)

        # Strategy: argument by constraint derivation for this hazard
        # Find UCAs that lead to this hazard
        incoming = _edges_of(all_edges, target_id=hid, conn_type="leads-to")
        uca_node_ids = {str(n["node_id"]) for n in _nodes_of(all_nodes, "unsafe-control-action")}
        uca_ids = [str(e["source_id"]) for e in incoming if str(e["source_id"]) in uca_node_ids]

        # Find constraints derived from those UCAs
        constraint_ids: list[str] = []
        for uid in uca_ids:
            derives = _edges_of(all_edges, source_id=uid, conn_type="derives")
            constraint_ids.extend(str(e["target_id"]) for e in derives)

        strategy: dict[str, object] = {
            "node_id": f"S-{hid}",
            "gsn_type": "strategy",
            "description": "Argument by constraint derivation from STPA UCAs",
            "source_hazard": hid,
            "uca_ids": uca_ids,
            "constraint_ids": constraint_ids,
        }
        strategies.append(strategy)

    # Solutions: evidence for each constraint
    solutions: list[dict[str, object]] = []
    constraints_without_evidence: list[dict[str, str]] = []
    hazards_without_constraints: list[dict[str, str]] = []

    for constraint in constraints:
        cid = str(constraint["node_id"])
        cname = str(constraint.get("name", cid))
        evidenced = _edges_of(all_edges, source_id=cid, conn_type="evidenced-by")
        evidence_ids = [str(e["target_id"]) for e in evidenced]

        if evidence_ids:
            for eid in evidence_ids:
                solutions.append({
                    "node_id": f"Sn-{eid}",
                    "gsn_type": "solution",
                    "description": f"Evidence for constraint '{cname}'",
                    "constraint_id": cid,
                    "evidence_id": eid,
                })
        else:
            constraints_without_evidence.append({"node_id": cid, "name": cname})

    # Identify hazards without any constraints via UCA chain
    for hazard in hazards:
        hid = str(hazard["node_id"])
        incoming = _edges_of(all_edges, target_id=hid, conn_type="leads-to")
        uca_node_ids = {str(n["node_id"]) for n in _nodes_of(all_nodes, "unsafe-control-action")}
        uca_ids = [str(e["source_id"]) for e in incoming if str(e["source_id"]) in uca_node_ids]
        has_constraint = False
        for uid in uca_ids:
            derives = _edges_of(all_edges, source_id=uid, conn_type="derives")
            if derives:
                has_constraint = True
                break
        if not has_constraint:
            hazards_without_constraints.append({
                "node_id": hid,
                "name": str(hazard.get("name", hid)),
            })

    return {
        "top_goal": top_goal,
        "sub_goals": sub_goals,
        "strategies": strategies,
        "solutions": solutions,
        "gaps": {
            "constraints_without_evidence": constraints_without_evidence,
            "hazards_without_constraints": hazards_without_constraints,
        },
    }


# ── Argument completeness ──────────────────────────────────────────────────────

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


def run_case_completeness(
    store: ConfidentialAssuranceStore,
    *,
    analysis_id: str | None = None,
) -> dict[str, object]:
    """Check argument completeness for an analysis-scoped store graph."""
    return case_completeness_from_records(*_analysis_graph(store, analysis_id))


def case_completeness_from_records(
    all_nodes: list[dict[str, object]],
    all_edges: list[dict[str, object]],
) -> dict[str, object]:
    """Check argument completeness for an assurance case.

    Checks:
      1. every assurance-constraint has ≥1 evidenced-by edge
      2. every hazard has ≥1 constraint via derives (from a UCA/loss-scenario)
      3. every loss has ≥1 hazard via leads-to

    Returns structured result with passed/checks/summary.
    """
    checks: dict[str, _CheckEntry] = {}

    # Check 1: every constraint has evidence
    constraints = _nodes_of(all_nodes, "assurance-constraint")
    no_evidence: list[dict[str, str]] = [
        {"node_id": str(c["node_id"]), "name": str(c.get("name", ""))}
        for c in constraints
        if not _edges_of(all_edges, source_id=str(c["node_id"]), conn_type="evidenced-by")
    ]
    _check(checks, "constraint_has_evidence", no_evidence)

    # Check 2: every hazard has ≥1 constraint (via UCA derives chain)
    hazards = _nodes_of(all_nodes, "hazard")
    hazards_no_constraint: list[dict[str, str]] = []
    for hazard in hazards:
        hid = str(hazard["node_id"])
        incoming = _edges_of(all_edges, target_id=hid, conn_type="leads-to")
        uca_node_ids = {str(n["node_id"]) for n in _nodes_of(all_nodes, "unsafe-control-action")}
        uca_ids = [str(e["source_id"]) for e in incoming if str(e["source_id"]) in uca_node_ids]
        has_constraint = False
        for uid in uca_ids:
            if _edges_of(all_edges, source_id=uid, conn_type="derives"):
                has_constraint = True
                break
        # Also check loss-scenario→derives for this hazard's UCA chain
        if not has_constraint:
            for uid in uca_ids:
                explains = _edges_of(all_edges, target_id=uid, conn_type="explains")
                for exp_edge in explains:
                    ls_id = str(exp_edge["source_id"])
                    if _edges_of(all_edges, source_id=ls_id, conn_type="derives"):
                        has_constraint = True
                        break
                if has_constraint:
                    break
        if not has_constraint:
            hazards_no_constraint.append({"node_id": hid, "name": str(hazard.get("name", ""))})
    _check(checks, "hazard_has_constraint", hazards_no_constraint)

    # Check 3: every loss has ≥1 hazard
    losses = _nodes_of(all_nodes, "loss")
    losses_no_hazard: list[dict[str, str]] = [
        {"node_id": str(loss["node_id"]), "name": str(loss.get("name", ""))}
        for loss in losses
        if not _edges_of(all_edges, target_id=str(loss["node_id"]), conn_type="leads-to")
    ]
    _check(checks, "loss_has_hazard", losses_no_hazard)

    all_passed = all(v["passed"] for v in checks.values())
    total_gaps = sum(v["gap_count"] for v in checks.values())
    failed_count = sum(1 for v in checks.values() if not v["passed"])
    summary = (
        "All argument-completeness checks passed."
        if all_passed
        else f"{total_gaps} completeness gap(s) found across {failed_count} check(s)."
    )

    return {"passed": all_passed, "checks": checks, "summary": summary}
