"""Promotion preflight check for assurance-constraints.

Blocks promotion when safety/security constraints lack an owner or evidence (§6).
Warns when constraints carry a TLP classification above WHITE (§23 promotion gate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.assurance_ports import ConfidentialAssuranceStore

_SAFETY_CLASSES = frozenset({"safety", "security"})
_CLASSIFIED_TLP = frozenset({"TLP:AMBER", "TLP:RED"})


def promotion_preflight(
    store: ConfidentialAssuranceStore,
    node_ids: list[str] | None = None,
) -> dict[str, object]:
    """Check safety/security constraints before promoting to a wider audience tier.

    Returns a dict with promote_safe flag, blocking issues, and TLP warnings.
    """
    candidates = store.list_nodes() if not node_ids else [
        n for n in store.list_nodes() if str(n["node_id"]) in set(node_ids)
    ]
    all_edges = store.list_edges()

    blocking: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    for node in candidates:
        if str(node.get("node_type", "")) != "assurance-constraint":
            continue
        nid = str(node["node_id"])
        concern_class = str(node.get("concern_class") or "")
        tlp = str(node.get("tlp") or "TLP:WHITE")

        if concern_class in _SAFETY_CLASSES:
            has_owner = any(
                str(e["target_id"]) == nid and str(e["conn_type"]) == "responsible-for"
                for e in all_edges
            )
            has_evidence = any(
                str(e["source_id"]) == nid and str(e["conn_type"]) == "evidenced-by"
                for e in all_edges
            )
            if not has_owner:
                blocking.append({
                    "node_id": nid,
                    "name": str(node.get("name", "")),
                    "issue": "missing_owner",
                    "message": (
                        f"Safety/security constraint ({concern_class}) has no responsible controller. "
                        "Add an incoming responsible-for connection before promoting (§6 pre-check)."
                    ),
                })
            if not has_evidence:
                blocking.append({
                    "node_id": nid,
                    "name": str(node.get("name", "")),
                    "issue": "missing_evidence",
                    "message": (
                        f"Safety/security constraint ({concern_class}) has no evidenced-by connection. "
                        "Add evidence before promoting (§6 pre-check)."
                    ),
                })

        if tlp in _CLASSIFIED_TLP:
            warnings.append({
                "node_id": nid,
                "name": str(node.get("name", "")),
                "tlp": tlp,
                "message": (
                    f"Constraint has TLP={tlp}. Promoting to a wider audience tier requires "
                    "explicit sign-off (§23 promotion gate)."
                ),
            })

    return {
        "promote_safe": len(blocking) == 0,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "blocking": blocking,
        "warnings": warnings,
    }
