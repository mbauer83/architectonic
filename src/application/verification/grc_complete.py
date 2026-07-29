"""§17(B) GRC control-coverage-complete profile checker.

Checks:
  - every in-scope obligation has ≥1 assurance-constraint via complies-with
  - every risk has a treatment attribute set
  - every risk has an owner: an incoming ``accountable-for`` edge from an
    organizational control-structure node (ISO 31000 risk ownership — the owner
    is answerable FOR the risk; the owner node may itself be bound to an
    architecture role via its binds-to reference)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.application.assurance_ports import ConfidentialAssuranceStore

class _CheckEntry(TypedDict):
    passed: bool
    gap_count: int
    gaps: list[dict[str, str]]


def _obligation_gaps(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Return obligations with no complies-with constraint."""
    gaps: list[dict[str, str]] = []
    for node in nodes:
        if str(node.get("node_type", "")) != "obligation":
            continue
        nid = str(node["node_id"])
        # complies-with edge goes from assurance-constraint → obligation (target=obligation)
        linked = any(
            str(e["target_id"]) == nid and str(e["conn_type"]) == "complies-with"
            for e in edges
        )
        if not linked:
            gaps.append({"node_id": nid, "name": str(node.get("name", ""))})
    return gaps


def _risk_no_treatment(nodes: list[dict[str, object]]) -> list[dict[str, str]]:
    """Return risk nodes with no treatment attribute."""
    gaps: list[dict[str, str]] = []
    for node in nodes:
        if str(node.get("node_type", "")) != "risk":
            continue
        attrs_raw = node.get("attributes_json") or "{}"
        try:
            attrs: dict[str, object] = json.loads(str(attrs_raw))
        except Exception:  # noqa: BLE001
            attrs = {}
        treatment = str(attrs.get("treatment") or "").strip()
        if not treatment:
            gaps.append({"node_id": str(node["node_id"]), "name": str(node.get("name", ""))})
    return gaps


def _risk_no_owner(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Return risk nodes with no owner: a risk is owned when a control-structure
    node is accountable FOR it (incoming ``accountable-for`` edge)."""
    gaps: list[dict[str, str]] = []
    for node in nodes:
        if str(node.get("node_type", "")) != "risk":
            continue
        nid = str(node["node_id"])
        has_owner_edge = any(
            str(e["target_id"]) == nid and str(e["conn_type"]) == "accountable-for"
            for e in edges
        )
        if has_owner_edge:
            continue
        gaps.append({"node_id": nid, "name": str(node.get("name", ""))})
    return gaps


def _check(checks: dict[str, _CheckEntry], key: str, gaps: list[dict[str, str]]) -> None:
    checks[key] = {
        "passed": len(gaps) == 0,
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def run_grc_complete(
    store: ConfidentialAssuranceStore,
    *,
    analysis_id: str | None = None,
) -> dict[str, object]:
    """Run §17(B) grc-control-coverage-complete checks.

    When ``analysis_id`` is given, only that analysis's nodes (and the edges and
    accountability arch-refs between/for them) are checked, so the wizard reports
    coverage for one unit of work.
    """
    all_nodes = store.list_nodes(analysis_id=analysis_id)
    if analysis_id is None:
        all_edges = store.list_edges()
        scoped_ids: set[str] | None = None
    else:
        scoped_ids = {str(n["node_id"]) for n in all_nodes}
        all_edges = [
            e for e in store.list_edges()
            if str(e.get("source_id")) in scoped_ids and str(e.get("target_id")) in scoped_ids
        ]

    checks: dict[str, _CheckEntry] = {}

    _check(checks, "obligation_has_constraint", _obligation_gaps(all_nodes, all_edges))
    _check(checks, "risk_has_treatment", _risk_no_treatment(all_nodes))
    _check(checks, "risk_has_owner", _risk_no_owner(all_nodes, all_edges))

    all_passed = all(v["passed"] for v in checks.values())
    total_gaps = sum(v["gap_count"] for v in checks.values())
    failed_count = sum(1 for v in checks.values() if not v["passed"])
    summary = (
        "All GRC coverage checks passed."
        if all_passed
        else f"{total_gaps} coverage gap(s) found across {failed_count} check(s)."
    )

    return {"passed": all_passed, "checks": checks, "summary": summary}
