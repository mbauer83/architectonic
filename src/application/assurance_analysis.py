"""Assurance analysis aggregate use cases (application layer).

An analysis is the aggregate root for a unit of STPA/CAST/GRC work: it is
anchored to one architecture artifact and owns the nodes created within it.
These use cases enforce the aggregate invariants (method vocabulary, required
architecture anchor, unlocked store) that the storage adapters do not.

MCP and HTTP adapters translate the typed outcomes into transport responses.
The architecture anchor is *optional*: it names the single system-under-analysis
element when one applies (typical for STPA/CAST), and may be empty for work that
spans several systems (typical for GRC). When supplied, anchor *existence* (the
artifact is real and visible) is validated by the calling adapter, which holds
the architecture-query port; this layer does not require an anchor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.domain.assurance.assurance_analysis import ANALYSIS_METHODS, ANALYSIS_STATUSES

if TYPE_CHECKING:
    from src.application.assurance_ports import AssuranceArchive, ConfidentialAssuranceStore

# ── Typed outcomes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnalysisOk:
    """Operation succeeded; payload is the analysis record or a list of them."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class AnalysisLocked:
    """Store not unlocked; translate to HTTP 423 / MCP locked envelope."""


@dataclass(frozen=True)
class AnalysisNotFound:
    """Analysis absent (or above ceiling); translate to HTTP 404 / MCP not_found."""

    analysis_id: str


@dataclass(frozen=True)
class AnalysisInvalid:
    """Request violated an aggregate invariant; translate to HTTP 400."""

    error: str
    message: str


AnalysisResult = AnalysisOk | AnalysisLocked | AnalysisNotFound | AnalysisInvalid


# ── Use cases ──────────────────────────────────────────────────────────────────


def create_analysis(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    name: str,
    method: str,
    architecture_anchor_id: str = "",
    tlp: str = "TLP:WHITE",
    status: str = "draft",
) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    if not name.strip():
        return AnalysisInvalid("missing_name", "An analysis requires a non-empty name.")
    if method not in ANALYSIS_METHODS:
        return AnalysisInvalid(
            "invalid_method",
            f"method must be one of {', '.join(ANALYSIS_METHODS)}; got {method!r}.",
        )
    if status not in ANALYSIS_STATUSES:
        return AnalysisInvalid(
            "invalid_status",
            f"status must be one of {', '.join(ANALYSIS_STATUSES)}; got {status!r}.",
        )
    analysis_id = store.create_analysis(
        name, method, architecture_anchor_id, tlp=tlp, status=status
    )
    archive.append(
        "CREATE_ANALYSIS",
        node_id=analysis_id,
        payload={"method": method, "name": name, "architecture_anchor_id": architecture_anchor_id},
    )
    record = store.get_analysis(analysis_id)
    return AnalysisOk(payload=record or {"analysis_id": analysis_id})


def list_analyses(
    store: ConfidentialAssuranceStore,
    *,
    method: str | None = None,
    status: str | None = None,
) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    return AnalysisOk(payload={"analyses": store.list_analyses(method=method, status=status)})


def get_analysis(store: ConfidentialAssuranceStore, analysis_id: str) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    record = store.get_analysis(analysis_id)
    if record is None:
        return AnalysisNotFound(analysis_id)
    return AnalysisOk(payload=record)


def update_analysis(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
    name: str | None = None,
    status: str | None = None,
    tlp: str | None = None,
) -> AnalysisResult:
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    if status is not None and status not in ANALYSIS_STATUSES:
        return AnalysisInvalid(
            "invalid_status",
            f"status must be one of {', '.join(ANALYSIS_STATUSES)}; got {status!r}.",
        )
    updates: dict[str, object] = {}
    for key, value in [("name", name), ("status", status), ("tlp", tlp)]:
        if value is not None:
            updates[key] = value
    if updates:
        store.update_analysis(analysis_id, **updates)
        archive.append("UPDATE_ANALYSIS", node_id=analysis_id, payload=dict(updates))
    return AnalysisOk(payload=store.get_analysis(analysis_id) or {"analysis_id": analysis_id})


def delete_analysis(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    analysis_id: str,
) -> AnalysisResult:
    """Delete an analysis. Blocks if it still owns member nodes (non-destructive default).

    The analysis is the aggregate root; deleting it must not silently destroy the
    member nodes. Callers detach or delete the member nodes first, then delete the
    (now empty) analysis. An abandoned/empty analysis deletes cleanly.
    """
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    member_count = len(store.list_nodes(analysis_id=analysis_id))
    if member_count > 0:
        return AnalysisInvalid(
            "analysis_not_empty",
            f"This analysis still owns {member_count} node(s). Reassign or delete its "
            "nodes before deleting the analysis.",
        )
    store.delete_analysis(analysis_id)
    archive.append("DELETE_ANALYSIS", node_id=analysis_id, payload={"analysis_id": analysis_id})
    return AnalysisOk(payload={"analysis_id": analysis_id, "deleted": True})
