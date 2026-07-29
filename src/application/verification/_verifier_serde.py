"""Serialisation/deserialisation helpers for incremental verifier state."""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_incremental import FileInventory
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    Issue,
    Severity,
    VerificationResult,
)


def results_from_state(prev: IncrementalState, inv: FileInventory) -> list[VerificationResult] | None:
    out: list[VerificationResult] = []
    for rel in inv.ordered_paths:
        raw = prev.results.get(rel)
        if not isinstance(raw, dict):
            return None
        parsed = deserialize_result(inv.rel_to_path[rel], raw)
        if parsed is None:
            return None
        out.append(parsed)
    return out


def merge_results(
    prev: IncrementalState, inv: FileInventory, fresh: list[VerificationResult]
) -> list[VerificationResult]:
    by_rel = {inv.path_to_rel[r.path]: r for r in fresh}
    merged: list[VerificationResult] = []
    for rel in inv.ordered_paths:
        if rel in by_rel:
            merged.append(by_rel[rel])
            continue
        raw = prev.results.get(rel)
        if not isinstance(raw, dict):
            return fresh
        parsed = deserialize_result(inv.rel_to_path[rel], raw)
        if parsed is None:
            return fresh
        merged.append(parsed)
    return merged


def deserialize_result(path: Path, data: dict) -> VerificationResult | None:
    file_type = data.get("file_type")
    if file_type not in {"entity", "connection", "diagram"}:
        return None
    issues_raw = data.get("issues", [])
    if not isinstance(issues_raw, list):
        return None
    issues: list[Issue] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            return None
        severity = item.get("severity")
        if severity not in {Severity.ERROR, Severity.WARNING}:
            return None
        code = item.get("code")
        message = item.get("message")
        location = item.get("location")
        if not all(isinstance(v, str) for v in [code, message, location]):
            return None
        raw_details = item.get("details")
        details = raw_details if isinstance(raw_details, dict) else None
        raw_actions = item.get("actions")
        actions: tuple | None = (
            tuple(a for a in raw_actions if isinstance(a, dict)) if isinstance(raw_actions, list) else None
        )
        issues.append(
            Issue(
                severity=severity,
                code=str(code),
                message=str(message),
                location=str(location),
                details=details,
                actions=actions,
            )
        )
    return VerificationResult(path=path, file_type=file_type, issues=issues)
