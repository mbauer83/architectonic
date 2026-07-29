"""Pure authorization policy for architecture-repository mutations.

Decides every mutation request against an immutable authorization snapshot:

* Standard authoring is engagement-only in EVERY mode and accepts only the
  configured active engagement root (canonically resolved — child paths, ``..``,
  relative and symlink spellings of anything else are rejected).
* Promotion — including enterprise save, submit, and discard — is the only
  enterprise write outside admin mode; admin mode enables direct enterprise
  authoring exclusively through the admin operations surface.
* Read-only denies all external repository intents; maintenance/recovery is
  always allowed.
* Health is reason- and action-aware (``denied_intents``): remote-connectivity
  faults deny remote-affecting workflow steps while local recovery (save, local
  discard) and engagement authoring stay available.
"""

from __future__ import annotations

from pathlib import Path

from src.application.mutation_authorization import (
    AuthorizationSnapshot,
    DiscardWrite,
    MutationAllowed,
    MutationDecision,
    MutationDenied,
    MutationIntent,
    MutationRequest,
    MutationTarget,
    PromotionWrite,
    RepositoryWrite,
    SyncHealthReason,
)

# Faults of the remote relationship (fetch/upstream/divergence): local commits and
# local branch discard remain safe and are the recovery path; only remote-affecting
# workflow steps are denied.
_REMOTE_RELATIONSHIP_FAULTS: frozenset[SyncHealthReason] = frozenset(
    {"fetch_failed", "upstream_missing", "diverged", "sync_state_unknown"}
)

# The sync aggregate itself is unusable: every enterprise workflow intent is denied
# until maintenance/recovery repairs it. Engagement authoring is untouched.
_AGGREGATE_FAULTS: frozenset[SyncHealthReason] = frozenset(
    {"state_file_corrupt", "repository_uninitialized"}
)

_ENTERPRISE_WORKFLOW_INTENTS: frozenset[MutationIntent] = frozenset(
    {"promotion", "enterprise_save", "enterprise_submit", "enterprise_discard"}
)


def denied_intents(reason: SyncHealthReason, target: MutationTarget) -> frozenset[MutationIntent]:
    """Intents denied by health *reason* for *target*.

    Never contains ``engagement_authoring``, ``enterprise_admin_authoring``, or
    ``maintenance``; ``enterprise_discard`` is denied under remote faults only in
    its pending-remote variant.
    """
    if reason in _REMOTE_RELATIONSHIP_FAULTS:
        denied: set[MutationIntent] = {"promotion", "enterprise_submit"}
        if isinstance(target, DiscardWrite) and target.pending_remote:
            denied.add("enterprise_discard")
        return frozenset(denied)
    return _ENTERPRISE_WORKFLOW_INTENTS


def authorize(snapshot: AuthorizationSnapshot, request: MutationRequest) -> MutationDecision:
    """Decide *request* against *snapshot*. Pure: no I/O beyond path resolution."""
    if request.intent == "maintenance":
        return MutationAllowed()
    if snapshot.read_only or snapshot.gate_block == "read_only":
        return MutationDenied(code="read_only", message="Workspace is read-only: all repository mutations are denied.")
    if snapshot.gate_block == "sync_in_progress":
        return MutationDenied(code="sync_in_progress", message="A sync is in progress: retry once it completes.")
    target_decision = _authorize_target(snapshot, request)
    if isinstance(target_decision, MutationDenied):
        return target_decision
    reason = snapshot.sync_health.reason
    if reason is not None and request.intent in denied_intents(reason, request.target):
        return MutationDenied(
            code="sync_health",
            message=f"Denied by enterprise sync health ({reason}): {snapshot.sync_health.message}".rstrip(": "),
            health_reason=reason,
        )
    return MutationAllowed()


def _authorize_target(snapshot: AuthorizationSnapshot, request: MutationRequest) -> MutationDecision:
    match request.intent, request.target:
        case "engagement_authoring", RepositoryWrite(root=root):
            return _check_engagement_root(snapshot, root)
        case "enterprise_admin_authoring", RepositoryWrite(root=root):
            if not snapshot.admin_mode:
                return MutationDenied(
                    code="admin_mode_required",
                    message="Direct enterprise authoring requires the backend to run in admin mode.",
                )
            return _check_enterprise_root(snapshot, root)
        case "promotion", PromotionWrite(source_root=source, destination_root=destination):
            source_decision = _check_engagement_root(snapshot, source)
            if isinstance(source_decision, MutationDenied):
                return source_decision
            return _check_enterprise_root(snapshot, destination)
        case ("enterprise_save" | "enterprise_submit"), RepositoryWrite(root=root):
            return _check_enterprise_root(snapshot, root)
        case "enterprise_discard", DiscardWrite(root=root):
            return _check_enterprise_root(snapshot, root)
        case _:
            return MutationDenied(
                code="target_shape_mismatch",
                message=f"Intent {request.intent!r} does not accept target {type(request.target).__name__}.",
            )


def _check_engagement_root(snapshot: AuthorizationSnapshot, root: Path) -> MutationDecision:
    resolved = root.resolve()
    if snapshot.engagement_root is not None and resolved == snapshot.engagement_root:
        return MutationAllowed()
    if snapshot.enterprise_root is not None and resolved.is_relative_to(snapshot.enterprise_root):
        return MutationDenied(
            code="enterprise_target_forbidden",
            message=(
                "Standard authoring never writes to the enterprise repository: promote from the "
                "engagement repository instead, or use the admin operations surface of an "
                "admin-mode backend for direct enterprise authoring."
            ),
        )
    return MutationDenied(
        code="target_not_engagement_root",
        message=f"Write target must be the configured active engagement root, got: {resolved}",
    )


def _check_enterprise_root(snapshot: AuthorizationSnapshot, root: Path) -> MutationDecision:
    resolved = root.resolve()
    if snapshot.enterprise_root is not None and resolved == snapshot.enterprise_root:
        return MutationAllowed()
    return MutationDenied(
        code="target_not_enterprise_root",
        message=f"Target must be the configured enterprise repository root, got: {resolved}",
    )
