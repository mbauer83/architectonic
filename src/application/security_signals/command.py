"""IngestSecuritySignals — the ONE application command owning the security-signal
snapshot lifecycle: typed bundle validation, idempotent-replay decision, staging
snapshot creation, population, completion, atomic activation, and failure recording
with safe diagnostics. Adapters (v1: the CLI/script surface only) submit a
bundle; nothing else may drive the low-level transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from src.application.security_signals.ports import AnchorReader, SnapshotStore
from src.domain.assurance.security_signal_snapshot import (
    AnchorTypeNotPermitted,
    AnchorUnknown,
    CreateNewSnapshot,
    IdempotencyConflict,
    ReplayInProgress,
    ReplayStoredFailure,
    ReplayStoredSuccess,
    StoredSnapshotKey,
    anchor_key,
    canonical_bundle_digest,
    evaluate_anchor,
    replay_decision,
)


@dataclass(frozen=True)
class IngestBundle:
    """The complete, normalized input of one ingest execution. Semantic fields
    only — snapshot ids and timestamps are generated downstream and excluded from
    the idempotency digest by construction."""

    anchor_entity_id: str
    request_id: str
    components: tuple[Mapping[str, object], ...]
    findings: tuple[Mapping[str, object], ...]
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    generator_metadata: Mapping[str, object] = field(default_factory=dict)
    source_metadata: Mapping[str, object] = field(default_factory=dict)
    bom_digest: str = ""
    bom_serial: str = ""
    bom_version: str = ""

    def __post_init__(self) -> None:
        # Normalize the anchor HERE, at the single choke point every write passes
        # through, so the stored key and the idempotency digest are both computed
        # on the stable id no matter which form the caller supplied.
        object.__setattr__(self, "anchor_entity_id", anchor_key(self.anchor_entity_id))

    def payload_digest(self) -> str:
        return canonical_bundle_digest({
            "anchor_entity_id": self.anchor_entity_id,
            "components": [dict(c) for c in self.components],
            "findings": [dict(f) for f in self.findings],
            "diagnostics": dict(self.diagnostics),
            "generator_metadata": dict(self.generator_metadata),
            "source_metadata": dict(self.source_metadata),
            "bom_digest": self.bom_digest,
            "bom_serial": self.bom_serial,
            "bom_version": self.bom_version,
        })


@dataclass(frozen=True)
class IngestValidationError:
    field: str
    message: str


def validate_bundle(bundle: IngestBundle) -> list[IngestValidationError]:
    errors: list[IngestValidationError] = []
    if not bundle.anchor_entity_id.strip():
        errors.append(IngestValidationError("anchor_entity_id", "anchor is required"))
    if not bundle.request_id.strip():
        errors.append(IngestValidationError("request_id", "request_id is required"))
    for index, component in enumerate(bundle.components):
        if not str(component.get("component_id") or ""):
            errors.append(IngestValidationError(
                "components", f"component[{index}] missing component_id"))
        if not str(component.get("name") or ""):
            errors.append(IngestValidationError(
                "components", f"component[{index}] missing name"))
    known = {str(c.get("component_id")) for c in bundle.components}
    for index, finding in enumerate(bundle.findings):
        if str(finding.get("component_id") or "") not in known:
            errors.append(IngestValidationError(
                "findings", f"finding[{index}] references unknown component_id"))
        raw_ids = finding.get("external_ids")
        if not (isinstance(raw_ids, (list, tuple)) and raw_ids):
            errors.append(IngestValidationError(
                "findings", f"finding[{index}] needs at least one external id"))
    return errors


# ── Typed outcomes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IngestActivated:
    """A successful ingest, reported as what the snapshot HOLDS plus what was
    submitted. ``persisted_*`` is what a subsequent read returns; the submitted
    counts and the collapse delta are carried alongside so the dedup is visible
    rather than looking like lost data."""

    snapshot_id: str
    superseded_snapshot_id: str | None
    submitted_component_count: int
    persisted_component_count: int
    submitted_finding_count: int
    persisted_finding_count: int

    @property
    def collapsed_finding_count(self) -> int:
        return self.submitted_finding_count - self.persisted_finding_count


@dataclass(frozen=True)
class IngestInvalid:
    errors: tuple[IngestValidationError, ...]


@dataclass(frozen=True)
class IngestReplayed:
    """Same key + digest replay: the stored outcome, verbatim; nothing mutated."""

    snapshot_id: str
    stored_outcome: str  # "in_progress" | "success" | "failed"
    message: str


@dataclass(frozen=True)
class IngestConflict:
    """Same key, different payload digest — typed idempotency conflict."""

    snapshot_id: str
    message: str


@dataclass(frozen=True)
class IngestFailed:
    """The execution failed mid-flight; the snapshot is recorded as failed."""

    snapshot_id: str
    reason: str


IngestResult = IngestActivated | IngestInvalid | IngestReplayed | IngestConflict | IngestFailed


def ingest_security_signals(
    bundle: IngestBundle,
    *,
    store: SnapshotStore,
    new_snapshot_id: Callable[[], str],
    anchor_reader: AnchorReader,
) -> IngestResult:
    """Execute one ingest: validate → check the anchor → replay decision → staging
    → populate → complete → activate. Any populate/complete/activate error records
    the snapshot as failed with a safe reason (failed is terminal — a retry needs a
    new request_id)."""
    errors = validate_bundle(bundle)
    if errors:
        return IngestInvalid(errors=tuple(errors))

    # The anchor is checked BEFORE anything is written. An ingest already requires
    # an anchor id, so accepting one that names nothing — or names something an
    # SBOM cannot describe — would store a snapshot the model can never reach.
    anchor_decision = evaluate_anchor(
        bundle.anchor_entity_id, anchor_reader.describe_anchor(bundle.anchor_entity_id))
    if isinstance(anchor_decision, AnchorUnknown):
        return IngestInvalid(errors=(IngestValidationError(
            "anchor_entity_id",
            f"no architecture entity {bundle.anchor_entity_id!r} exists; "
            "signals must anchor on an entity in the model",
        ),))
    if isinstance(anchor_decision, AnchorTypeNotPermitted):
        return IngestInvalid(errors=(
            IngestValidationError("anchor_entity_id", anchor_decision.message()),))

    digest = bundle.payload_digest()
    existing = store.find_snapshot_by_request(bundle.anchor_entity_id, bundle.request_id)
    stored = None if existing is None else StoredSnapshotKey(
        snapshot_id=str(existing["snapshot_id"]),
        status=str(existing["status"]),
        request_payload_digest=str(existing["request_payload_digest"]),
    )
    decision = replay_decision(stored, digest)
    if isinstance(decision, ReplayInProgress):
        return IngestReplayed(snapshot_id=decision.snapshot_id, stored_outcome="in_progress",
                               message="An ingest for this request is in progress; retry later.")
    if isinstance(decision, ReplayStoredSuccess):
        return IngestReplayed(snapshot_id=decision.snapshot_id, stored_outcome="success",
                               message="This request already succeeded; returning the original snapshot.")
    if isinstance(decision, ReplayStoredFailure):
        return IngestReplayed(snapshot_id=decision.snapshot_id, stored_outcome="failed",
                               message="This request previously failed; submit with a new request_id.")
    if isinstance(decision, IdempotencyConflict):
        return IngestConflict(
            snapshot_id=decision.snapshot_id,
            message="request_id was already used with a different payload; nothing was written.",
        )
    assert isinstance(decision, CreateNewSnapshot)

    snapshot_id = new_snapshot_id()
    store.create_staging_snapshot(
        snapshot_id=snapshot_id,
        anchor_entity_id=bundle.anchor_entity_id,
        request_id=bundle.request_id,
        request_payload_digest=digest,
        bom_digest=bundle.bom_digest,
        bom_serial=bundle.bom_serial,
        bom_version=bundle.bom_version,
        generator_metadata=bundle.generator_metadata,
        source_metadata=bundle.source_metadata,
        diagnostics=bundle.diagnostics,
    )
    try:
        population = store.populate_snapshot(
            snapshot_id, components=bundle.components, findings=bundle.findings)
        store.complete_snapshot(snapshot_id)
        activation = store.activate_snapshot(snapshot_id)
    except Exception as exc:  # noqa: BLE001 — recorded as a failed snapshot, safe reason only
        reason = f"{type(exc).__name__} during ingest execution"
        store.fail_snapshot(snapshot_id, reason=reason)
        return IngestFailed(snapshot_id=snapshot_id, reason=reason)
    superseded = activation.get("superseded_snapshot_id")
    # Counts come from the population, never from len(bundle.*): the store
    # collapses findings resolving to one canonical vulnerability per component,
    # so the submitted length is not what the caller will read back.
    return IngestActivated(
        snapshot_id=snapshot_id,
        superseded_snapshot_id=str(superseded) if superseded else None,
        submitted_component_count=population.submitted_component_count,
        persisted_component_count=population.persisted_component_count,
        submitted_finding_count=population.submitted_finding_count,
        persisted_finding_count=population.persisted_finding_count,
    )
