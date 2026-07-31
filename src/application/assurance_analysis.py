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
    """Request violated an aggregate invariant. ``error`` names which; the adapter maps it to a status.

    ``subject`` and ``count`` carry the *structured* context behind the message, for the codes whose
    published details declare it. The message alone is not enough: a client showing "this analysis
    authored 3 nodes" from prose has to parse a sentence, and the delivery layer building the declared
    ``details`` payload has nothing to build it from. Empty and zero for the codes that carry neither.
    """

    error: str
    message: str
    subject: str = ""
    count: int = 0


@dataclass(frozen=True)
class AnalysisLegacyInvalid:
    """A node awaiting provenance repair; only provenance assignment may touch it.

    Declared beside the other analysis outcomes rather than borrowed from the mutation module, so
    the participation use cases keep one result union.
    """

    node_id: str
    permitted_operation: str = "assign_provenance"


AnalysisResult = (
    AnalysisOk | AnalysisLocked | AnalysisNotFound | AnalysisInvalid | AnalysisLegacyInvalid
)


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
    """Delete an analysis that authored nothing, and the participation rows naming it.

    Refused while the analysis has authored nodes. No reassignment is offered, and the old guidance
    to "detach or delete" them is gone: provenance is immutable, so detaching is not a thing a
    caller can do. The nodes either stay — visibly authored by an analysis that still exists — or
    are explicitly deleted first.

    Participation is the opposite case. A node another analysis merely *borrowed* is not this
    analysis's to keep or destroy, so the analysis goes and the borrowing relation goes with it,
    while the node and its provenance are untouched. That cleanup is the store's, in one unit of
    work with the deletion, because participation has no foreign key to analyses in any backend.
    """
    if not store.is_unlocked():
        return AnalysisLocked()
    if store.get_analysis(analysis_id) is None:
        return AnalysisNotFound(analysis_id)
    authored_count = len(store.list_nodes(analysis_id=analysis_id))
    if authored_count > 0:
        return AnalysisInvalid(
            "analysis_not_empty",
            f"This analysis authored {authored_count} node(s), and provenance is immutable — they "
            "cannot be reassigned. Delete them explicitly, or leave the analysis in place.",
            subject=analysis_id,
            count=authored_count,
        )
    store.delete_analysis(analysis_id)
    archive.append("DELETE_ANALYSIS", node_id=analysis_id, payload={"analysis_id": analysis_id})
    return AnalysisOk(payload={"analysis_id": analysis_id, "deleted": True})
