"""Application services for analysis-scoped GSN drafting and publication records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from src.application.verification.case_draft import draft_gsn_from_records, draft_gsn_from_store
from src.domain.assurance.classification import TLP_ORDER, is_publishable, normalize_tlp, tlp_rank

if TYPE_CHECKING:
    from src.application.assurance_ports import AssuranceArchive, ConfidentialAssuranceStore


def _node(
    node_id: str,
    name: str,
    gsn_type: str,
    source_ids: list[str],
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "name": name,
        "gsn_type": gsn_type,
        "source_assurance_ids": source_ids,
    }


def _diagram_entities(
    draft: dict[str, object],
    analysis: dict[str, object],
) -> dict[str, object]:
    top_value = draft["top_goal"]
    top = dict(top_value) if isinstance(top_value, Mapping) else {}
    sub_goals = _dict_list(draft["sub_goals"])
    strategies = _dict_list(draft["strategies"])
    solutions = _dict_list(draft["solutions"])

    nodes = [
        _node(
            str(top["node_id"]),
            str(top["claim"]),
            "goal",
            [str(item) for item in top.get("source_losses", [])],
        ),
        _node(
            "C-ANALYSIS",
            f"Analysis: {analysis.get('name', analysis.get('analysis_id', ''))}",
            "context",
            [],
        ),
    ]
    edges: list[dict[str, str]] = [
        {"source_id": str(top["node_id"]), "target_id": "C-ANALYSIS", "conn_type": "in-context-of"}
    ]
    strategies_by_hazard = {str(item["source_hazard"]): item for item in strategies}
    sub_goals_by_hazard = {str(item["source_hazard"]): item for item in sub_goals}
    added_solution_ids: set[str] = set()
    for hazard_id, goal in sub_goals_by_hazard.items():
        strategy = strategies_by_hazard[hazard_id]
        strategy_id = str(strategy["node_id"])
        goal_id = str(goal["node_id"])
        nodes.extend([
            _node(
                strategy_id,
                str(strategy["description"]),
                "strategy",
                [hazard_id, *_str_list(strategy.get("uca_ids"))],
            ),
            _node(goal_id, str(goal["claim"]), "goal", [hazard_id]),
        ])
        edges.extend([
            {"source_id": str(top["node_id"]), "target_id": strategy_id, "conn_type": "supported-by"},
            {"source_id": strategy_id, "target_id": goal_id, "conn_type": "supported-by"},
        ])
        constraint_ids = set(_str_list(strategy.get("constraint_ids")))
        for solution in solutions:
            if str(solution.get("constraint_id")) not in constraint_ids:
                continue
            solution_id = str(solution["node_id"])
            if solution_id in added_solution_ids:
                continue
            added_solution_ids.add(solution_id)
            nodes.append(
                _node(
                    solution_id,
                    str(solution["description"]),
                    "solution",
                    [str(solution["constraint_id"]), str(solution["evidence_id"])],
                )
            )
            edges.append({"source_id": goal_id, "target_id": solution_id, "conn_type": "supported-by"})
    return {"nodes": nodes, "edges": edges}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _str_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _effective_tlp(
    analysis: dict[str, object],
    nodes: list[dict[str, object]],
) -> str:
    levels = [normalize_tlp(str(analysis.get("tlp") or "TLP:AMBER"))]
    levels.extend(normalize_tlp(str(node.get("tlp") or "TLP:WHITE")) for node in nodes)
    return max(levels, key=tlp_rank)


def build_gsn_draft(
    store: ConfidentialAssuranceStore,
    *,
    analysis_id: str,
    visible_nodes: list[dict[str, object]] | None = None,
    visible_edges: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    analysis = store.get_analysis(analysis_id)
    if analysis is None:
        return None
    nodes = visible_nodes if visible_nodes is not None else store.list_nodes(analysis_id=analysis_id)
    draft = (
        draft_gsn_from_records(nodes, visible_edges or [])
        if visible_nodes is not None
        else draft_gsn_from_store(store, analysis_id=analysis_id)
    )
    effective_tlp = _effective_tlp(analysis, nodes)
    return {
        "analysis": analysis,
        "draft": draft,
        "diagram_entities": _diagram_entities(draft, analysis),
        "effective_tlp": effective_tlp,
        "publishable": is_publishable(effective_tlp),
        "classification_order": list(TLP_ORDER),
    }


def record_publication(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
    diagram_id: str,
    source_bindings: list[dict[str, str]],
) -> dict[str, object]:
    draft = build_gsn_draft(store, analysis_id=analysis_id)
    if draft is None:
        return {"error": "analysis_not_found", "analysis_id": analysis_id}
    if not bool(draft["publishable"]):
        return {"error": "classification_not_publishable", "effective_tlp": draft["effective_tlp"]}
    registered = 0
    for binding in source_bindings:
        assurance_id = binding.get("assurance_node_id", "")
        gsn_node_id = binding.get("gsn_node_id", "")
        if not assurance_id or store.get_node(assurance_id) is None:
            continue
        store.register_arch_ref(assurance_id, f"{diagram_id}#nodes/{gsn_node_id}", "gsn-source")
        registered += 1
    archive.append(
        "PUBLISH_GSN",
        payload={
            "analysis_id": analysis_id,
            "diagram_id": diagram_id,
            "effective_tlp": draft["effective_tlp"],
            "binding_count": registered,
        },
    )
    return {"status": "published", "diagram_id": diagram_id, "binding_count": registered}
