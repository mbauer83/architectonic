"""Verifier rule: a diagram's purpose line — who it is for and what it answers.

E185: the `stakeholders` or `concerns` value cannot be read. E186: an entry refers to an element the
repository does not hold. E187: it refers to one of a type that cannot stand in that list — what can is the
ontology's declaration (`purpose_line_elements`), resolved by the catalog, so this rule names no type.
Whether a reference resolves is `purpose_line_references`' to decide, the same check a viewpoint
definition's lines go through; this rule only spells its findings as diagram codes.

Every write path verifies before it keeps a file, so these are also how a create or an edit naming a
missing or unsuitable element is refused.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.verification.purpose_line_references import (
    Missing,
    PurposeLineResolution,
    ReferenceFault,
    Unsuitable,
)
from src.domain.purpose_lines import MalformedPurposeLine, read_purpose_lines


def check_purpose_lines(
    fm: Mapping[str, object], resolution: PurposeLineResolution, result: VerificationResult, loc: str
) -> None:
    """Report a purpose line that cannot be read, and every reference that does not resolve to a suitable element."""
    try:
        lines = read_purpose_lines(fm)
    except MalformedPurposeLine as malformed:
        result.issues.append(Issue(Severity.ERROR, "E185", str(malformed), loc))
        return
    result.issues.extend(
        Issue(Severity.ERROR, _code(unresolved.fault), unresolved.describe(), loc)
        for unresolved in resolution.unresolved(lines)
    )


def _code(fault: ReferenceFault) -> str:
    match fault:
        case Missing():
            return "E186"
        case Unsuitable():
            return "E187"
