"""Filing and participation use cases (application layer).

Two aggregate-crossing gestures that the storage adapters deliberately do not police:

* **Filing** an analysis into a group. The group must exist, because an analysis filed under an
  id nothing answers to is invisible in a tree keyed by group — worse than unfiled, which at
  least has a home.
* **Participation** — drawing a node into an analysis that did not author it. Both ends must
  exist, and neither is modified: the node keeps its author, and the analysis gains no copy.

Authorship stays where it is. `assurance_nodes.analysis_id` says who produced a node and is not
touched here; these use cases only add the second, many-to-many relation on top, which is what
lets an FMEA reason over an STPA's control structure without duplicating it.

The typed outcomes are the analysis aggregate's, reused rather than restated: an adapter that
already translates `AnalysisNotFound` into a 404 needs no second table of meanings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.assurance.analysis import (
    AnalysisInvalid,
    AnalysisLegacyInvalid,
    AnalysisLocked,
    AnalysisNotFound,
    AnalysisOk,
    AnalysisResult,
)
from src.application.assurance.legacy_invalid import refuse_if_legacy_invalid

if TYPE_CHECKING:
    from src.application.assurance.ports import AssuranceArchive, ConfidentialAssuranceStore


# ── Groups ─────────────────────────────────────────────────────────────────────


def create_group(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    name: str,
    description: str = "",
) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    if not name.strip():
        return AnalysisInvalid("missing_name", "A group requires a non-empty name.")
    group_id = store.create_group(name, description)
    archive.append("CREATE_GROUP", node_id=group_id, payload={"name": name})
    record = store.get_group(group_id)
    return AnalysisOk(payload=record or {"group_id": group_id})


def list_groups(store: ConfidentialAssuranceStore) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    return AnalysisOk(payload={"groups": store.list_groups()})


def delete_group(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    group_id: str,
) -> AnalysisResult:
    """Delete the group. Its analyses survive, unfiled — see the port's contract."""
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_group(group_id) is None:
        return AnalysisNotFound(group_id)
    unfiled = [
        str(analysis["analysis_id"])
        for analysis in store.list_analyses()
        if str(analysis.get("group_id") or "") == group_id
    ]
    store.delete_group(group_id)
    archive.append("DELETE_GROUP", node_id=group_id, payload={"unfiled_analyses": unfiled})
    return AnalysisOk(payload={"group_id": group_id, "deleted": True, "unfiled_analyses": unfiled})


def file_analysis(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
    group_id: str | None,
) -> AnalysisResult:
    """File the analysis into ``group_id``, or unfile it when that is None.

    Unfiling is a first-class outcome rather than an error: an analysis is worth recording before
    anyone settles where it belongs, so it has to be possible to take it back out again.
    """
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    if group_id is not None and store.get_group(group_id) is None:
        return AnalysisInvalid(
            "group_not_found",
            f"No group {group_id!r} exists. Filing an analysis under an id nothing answers to "
            "would hide it from every view keyed by group.",
        )
    store.update_analysis(analysis_id, group_id=group_id)
    archive.append("FILE_ANALYSIS", node_id=analysis_id, payload={"group_id": group_id})
    return AnalysisOk(payload=store.get_analysis(analysis_id) or {"analysis_id": analysis_id})


# ── Participation ──────────────────────────────────────────────────────────────


def add_participant(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
    node_id: str,
) -> AnalysisResult:
    """Draw an existing node into ``analysis_id`` without changing who authored it."""
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    if store.get_node(node_id) is None:
        return AnalysisNotFound(node_id)
    blocked = refuse_if_legacy_invalid(store, node_id)
    if blocked is not None:
        # A node awaiting provenance repair cannot be drawn into a second analysis: participation
        # says another method builds on its work, and there is no recorded author to build on yet.
        return AnalysisLegacyInvalid(node_id=blocked.node_id)
    store.add_analysis_member(analysis_id, node_id)
    archive.append(
        "ADD_ANALYSIS_MEMBER", node_id=node_id, payload={"analysis_id": analysis_id}
    )
    return AnalysisOk(payload={
        "analysis_id": analysis_id,
        "node_id": node_id,
        "participating": True,
    })


def remove_participant(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
    node_id: str,
) -> AnalysisResult:
    """Stop a node participating. The node itself is untouched.

    An absent membership is not an error: the caller asked for a state, and the state holds.
    A missing *analysis* still is — it means the caller is addressing something that never
    existed, which is worth telling them.
    """
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    store.remove_analysis_member(analysis_id, node_id)
    archive.append(
        "REMOVE_ANALYSIS_MEMBER", node_id=node_id, payload={"analysis_id": analysis_id}
    )
    return AnalysisOk(payload={
        "analysis_id": analysis_id,
        "node_id": node_id,
        "participating": False,
    })
