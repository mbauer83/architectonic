"""Verifier rule: an edge-label override that names no relation the diagram draws (E410)."""

from __future__ import annotations

from src.application.modeling.diagram_identities import drawn_relation_ends
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.diagrams.relation_key import MalformedRelationKey, read_relation_key


def check_edge_label_overrides(fm: dict, result: VerificationResult, loc: str) -> None:
    """Flag every ``edge-labels`` key that is not the key of a relation this diagram draws.

    A label is keyed by its drawn relation — the connection, and the instances at its ends where
    either is a further occurrence — so the question is asked of what the diagram records, not of
    the arrows in its body. A key in the retired alias-pair form is refused with what to run.
    """
    raw = fm.get("edge-labels")
    if not isinstance(raw, dict) or not raw:
        return
    drawn = drawn_relation_ends(fm.get("connection-ids-used"), fm.get("diagram-entities"), fm.get("connections"))
    for key in raw:
        try:
            named = read_relation_key(str(key)).text
        except MalformedRelationKey as refusal:
            result.issues.append(Issue(Severity.ERROR, "E410", f"edge-labels: {refusal}", loc))
            continue
        if named not in drawn:
            result.issues.append(Issue(
                Severity.ERROR,
                "E410",
                f"edge-labels key '{key}' names no relation this diagram draws (dangling override)",
                loc,
            ))
