"""The one submission boundary for security-signal ingestion.

Every ingest surface — the dogfooding script, the REST route, the MCP tool —
assembles a typed bundle here, submits it through the same serialised write, and
renders the outcome through the same projection, so snapshot-id policy, the
single-writer boundary, and the response shape each have exactly one definition.
Acquisition is injected (`acquire`): live OSV querying for the script,
caller-supplied records for the REST/MCP surfaces. No surface touches the snapshot
lifecycle directly — the IngestSecuritySignals command owns staging → populate
→ complete → activate.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable, Mapping, Sequence

from src.application.security_signals.bundle_assembly import (
    AcquisitionInputs,
    attach_findings,
    prepare_components,
)
from src.application.security_signals.command import (
    IngestActivated,
    IngestBundle,
    IngestConflict,
    IngestFailed,
    IngestInvalid,
    IngestReplayed,
    IngestResult,
    ingest_security_signals,
)
from src.application.security_signals.ports import AnchorReader, SnapshotStore

Acquire = Callable[[Sequence[Mapping[str, str]]], AcquisitionInputs]


def new_snapshot_id() -> str:
    return f"SNAP@{uuid.uuid4().hex[:16]}"


def new_request_id() -> str:
    return f"ingest-{uuid.uuid4()}"


def assemble_bundle(
    anchor_entity_id: str,
    sbom_data: Mapping[str, Any],
    *,
    acquire: Acquire,
    request_id: str = "",
    generator_metadata: Mapping[str, object] | None = None,
    source_metadata: Mapping[str, object] | None = None,
) -> IngestBundle:
    """Parse a CycloneDX document, classify its components, acquire vulnerability
    data through the injected strategy, and return the complete typed bundle."""
    from src.infrastructure.assurance._sbom_parser import parse_bom  # noqa: PLC0415

    bom_digest = hashlib.sha256(
        json.dumps(dict(sbom_data), sort_keys=True, default=str).encode()).hexdigest()
    meta, parsed = parse_bom(dict(sbom_data))
    assembled = prepare_components(meta, parsed)
    attach_findings(assembled, acquire(assembled.queryable))
    return IngestBundle(
        anchor_entity_id=anchor_entity_id,
        request_id=request_id or new_request_id(),
        components=tuple(assembled.components),
        findings=tuple(assembled.findings),
        diagnostics=assembled.diagnostics,
        generator_metadata=dict(generator_metadata or {}),
        source_metadata=dict(source_metadata or {}),
        bom_digest=bom_digest,
        bom_serial=str(meta.get("bom_serial") or ""),
        bom_version=str(meta.get("bom_version") or ""),
    )


def submit_bundle(
    bundle: IngestBundle,
    *,
    snapshot_store: SnapshotStore,
    anchor_reader: AnchorReader | None = None,
) -> IngestResult:
    """Execute one ingest on the serialised assurance writer.

    The anchor reader is resolved here when not supplied, so every transport gets
    anchor validation without each one wiring it — a surface that forgot would
    otherwise accept anchors the others refuse.
    """
    from src.infrastructure.assurance.anchor_reader import anchor_reader_for  # noqa: PLC0415
    from src.infrastructure.assurance.write_serialization import run_write  # noqa: PLC0415

    reader = anchor_reader if anchor_reader is not None else anchor_reader_for()
    return run_write(lambda: ingest_security_signals(
        bundle, store=snapshot_store, new_snapshot_id=new_snapshot_id,
        anchor_reader=reader,
    ))


def ingest_supplied_bom(
    anchor_entity_id: str,
    bom: Mapping[str, Any],
    *,
    records: Sequence[Mapping[str, Any]],
    snapshot_store: SnapshotStore,
    request_id: str = "",
    source: str = "",
    anchor_reader: AnchorReader | None = None,
) -> IngestResult:
    """Ingest a caller-supplied BOM (+ advisories) for one anchor.

    The whole act behind both the REST route and the MCP tool: assemble the bundle
    with supplied-record acquisition, then submit it. Callers gate on the
    signal-mutation capability first — they render a denial differently, but the
    ingest itself is defined once, here.
    """
    from src.application.security_signals.supplied_acquisition import (  # noqa: PLC0415
        acquisition_from_records,
    )

    bundle = assemble_bundle(
        anchor_entity_id,
        bom,
        acquire=lambda queryable: acquisition_from_records(queryable, records),
        request_id=request_id,
        generator_metadata={"generator": "supplied-bom"},
        source_metadata={"vulnerability_source": source or "caller-supplied"},
    )
    return submit_bundle(
        bundle, snapshot_store=snapshot_store, anchor_reader=anchor_reader)


# HTTP status per ingest outcome; the MCP surface reports the same `status`
# string and ignores the code, so both transports stay in lockstep.
INGEST_STATUS_CODES: Mapping[str, int] = {
    "activated": 200,
    "replayed": 200,  # idempotent replay: the stored outcome, nothing written
    "invalid": 422,
    "conflict": 409,  # request_id reused with a different payload
    "failed": 500,
}


def ingest_outcome_payload(result: IngestResult) -> dict[str, object]:
    """Project the command's typed outcome onto the shared response body."""
    match result:
        case IngestActivated() as activated:
            # `component_count`/`finding_count` are the PERSISTED counts — what a
            # read of this snapshot returns. The submitted counts and the collapse
            # delta ride alongside so a caller seeing fewer findings than it sent
            # can tell alias dedup from data loss.
            return {
                "status": "activated",
                "snapshot_id": activated.snapshot_id,
                "superseded_snapshot_id": activated.superseded_snapshot_id,
                "component_count": activated.persisted_component_count,
                "finding_count": activated.persisted_finding_count,
                "submitted_component_count": activated.submitted_component_count,
                "submitted_finding_count": activated.submitted_finding_count,
                "collapsed_finding_count": activated.collapsed_finding_count,
            }
        case IngestInvalid(errors):
            return {
                "status": "invalid",
                "errors": [{"field": e.field, "message": e.message} for e in errors],
            }
        case IngestReplayed(snapshot_id, outcome, message):
            return {
                "status": "replayed",
                "snapshot_id": snapshot_id,
                "stored_outcome": outcome,
                "message": message,
            }
        case IngestConflict(snapshot_id, message):
            return {"status": "conflict", "snapshot_id": snapshot_id, "message": message}
        case IngestFailed(snapshot_id, reason):
            return {"status": "failed", "snapshot_id": snapshot_id, "reason": reason}
