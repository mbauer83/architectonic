"""Verifier rule: a diagram's purpose line — who it is for and what it answers.

E185: the `stakeholders` or `concerns` value cannot be read. E186: an entry refers to an element the
repository does not hold. E187: it refers to one of a type that cannot stand in that list — what can is the
ontology's declaration (`purpose_line_elements`), resolved by the catalog, so this rule names no type.

Every write path verifies before it keeps a file, so these are also how a create or an edit naming a
missing or unsuitable element is refused.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.ontology_representation.purpose_line_elements import PurposeLineTypes
from src.domain.purpose_lines import STAKEHOLDERS_KEY, MalformedPurposeLine, Reference, read_purpose_lines

_ROLE = {STAKEHOLDERS_KEY: "a stakeholder"}


def _admitted(types: PurposeLineTypes, key: str) -> frozenset[str]:
    return types.stakeholders if key == STAKEHOLDERS_KEY else types.concerns


def _reference_issue(
    key: str, reference: Reference, registry: ArtifactRegistry, types: PurposeLineTypes, loc: str
) -> Issue | None:
    entity = registry.get_entity(reference.artifact_id)
    if entity is None:
        return Issue(
            Severity.ERROR, "E186",
            f"'{key}' refers to '{reference.artifact_id}', which this repository does not hold", loc,
        )
    admitted = _admitted(types, key)
    if entity.artifact_type in admitted:
        return None
    role = _ROLE.get(key, "the element stating a concern")
    return Issue(
        Severity.ERROR, "E187",
        f"'{key}' refers to '{reference.artifact_id}', a {entity.artifact_type}, which cannot stand as {role}; "
        f"admitted types: {', '.join(sorted(admitted)) or 'none — state it in words'}",
        loc,
    )


def check_purpose_lines(
    fm: Mapping[str, object], registry: ArtifactRegistry, types: PurposeLineTypes, result: VerificationResult, loc: str
) -> None:
    """Report a purpose line that cannot be read, and every reference that does not resolve to a suitable element."""
    try:
        lines = read_purpose_lines(fm)
    except MalformedPurposeLine as malformed:
        result.issues.append(Issue(Severity.ERROR, "E185", str(malformed), loc))
        return
    result.issues.extend(
        issue for key, reference in lines.references()
        if (issue := _reference_issue(key, reference, registry, types, loc)) is not None
    )
