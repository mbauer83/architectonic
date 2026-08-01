"""Per-request authority projection for the sync status read model.

Composed FRESH on every status request from the same snapshot provider the
mutation executor enforces with — authority is never cached, so a live
``gate.blocking_writes()`` transition or a persisted health change is visible
to the very next request with no TTL. The projection is per-intent
(``denied_intents`` with denial codes), and a tab joining during a transient
block reconstructs it entirely from this snapshot.
"""

from __future__ import annotations

from typing import Any, Literal

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    DiscardWrite,
    MutationDenied,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)
from src.application.mutation_policy import authorize

BlockKind = Literal["none", "read_only", "sync_in_progress", "sync_health"]

WORKFLOW_ACTIONS = (
    "engagement_authoring",
    "enterprise_admin_authoring",
    "promotion",
    "enterprise_save",
    "enterprise_submit",
    "enterprise_discard_local",
    "enterprise_discard_pending",
    "maintenance",
)


def _request_for(action: str, snapshot: AuthorizationSnapshot) -> MutationRequest | None:
    engagement = snapshot.engagement_root
    enterprise = snapshot.enterprise_root
    match action:
        case "engagement_authoring":
            return MutationRequest("engagement_authoring", RepositoryWrite(engagement)) if engagement else None
        case "enterprise_admin_authoring":
            return MutationRequest("enterprise_admin_authoring", RepositoryWrite(enterprise)) if enterprise else None
        case "promotion":
            if engagement is None or enterprise is None:
                return None
            return MutationRequest("promotion", PromotionWrite(engagement, enterprise))
        case "enterprise_save":
            return MutationRequest("enterprise_save", RepositoryWrite(enterprise)) if enterprise else None
        case "enterprise_submit":
            return MutationRequest("enterprise_submit", RepositoryWrite(enterprise)) if enterprise else None
        case "enterprise_discard_local":
            if enterprise is None:
                return None
            return MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=False))
        case "enterprise_discard_pending":
            if enterprise is None:
                return None
            return MutationRequest("enterprise_discard", DiscardWrite(enterprise, pending_remote=True))
        case "maintenance":
            return MutationRequest("maintenance", RepositoryWrite(engagement)) if engagement else None
    return None


def _block_kind(snapshot: AuthorizationSnapshot) -> BlockKind:
    if snapshot.read_only or snapshot.gate_block == "read_only":
        return "read_only"
    if snapshot.gate_block == "sync_in_progress":
        return "sync_in_progress"
    if snapshot.sync_health.reason is not None:
        return "sync_health"
    return "none"


def authority_projection(snapshot: AuthorizationSnapshot) -> dict[str, Any]:
    """The per-intent authority view every status response carries."""
    denied: dict[str, dict[str, Any]] = {}
    for action in WORKFLOW_ACTIONS:
        request = _request_for(action, snapshot)
        if request is None:
            denied[action] = {"denied": True, "code": "not_configured"}
            continue
        decision = authorize(snapshot, request)
        if isinstance(decision, MutationDenied):
            denied[action] = {"denied": True, "code": decision.code}
        else:
            denied[action] = {"denied": False, "code": None}
    return {
        "block_kind": _block_kind(snapshot),
        "blocked_reason": snapshot.sync_health.reason,
        "blocked_message": snapshot.sync_health.message or None,
        "denied_intents": denied,
    }
