"""Proposed-change verifier rules.

E145: `proposes-change-to` missing or empty.
E146: the global artifact reference it names is not in the repository.
E147: `recorded-edit` missing, malformed, or naming something not editable.
E148: `base-revision` missing or empty.
E149: `proposal-state` is not one of the four.
W145: cannot check the reference because the repository index is not loaded.

Staleness is deliberately absent. Whether the enterprise artifact has moved past the base revision
is answered against a repository at the moment someone asks, and a verifier that reads a file cannot
ask it. Recording the answer in the file would be worse: it would go wrong quietly the moment the
enterprise repository moved, which is the normal case rather than the exception.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.application.modeling.proposal_edit import UnproposableEdit, from_mapping
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
    STATES,
)
from src.application.verification.artifact_verifier_types import (
    Issue,
    Severity,
    SeverityLiteral,
    VerificationResult,
)

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry


def _issue(
    result: VerificationResult, severity: SeverityLiteral, code: str, message: str, loc: str
) -> None:
    result.issues.append(Issue(severity, code, message, loc))


def check_proposed_change(
    fm: dict,
    registry: "ArtifactRegistry | None",
    result: VerificationResult,
    loc: str,
) -> None:
    """Validate a proposed-change entity. Each field is checked independently.

    Independently on purpose: an author who has three things wrong should be told three things, and
    the first missing field is no reason to stop reading the rest.
    """
    _check_reference(fm, registry, result, loc)
    _check_recorded_edit(fm, result, loc)
    _check_base_revision(fm, result, loc)
    _check_state(fm, result, loc)


def _check_reference(
    fm: dict, registry: "ArtifactRegistry | None", result: VerificationResult, loc: str
) -> None:
    reference = fm.get(PROPOSES_CHANGE_TO)
    if not reference:
        _issue(result, Severity.ERROR, "E145",
               f"proposed-change is missing required '{PROPOSES_CHANGE_TO}' field", loc)
        return
    if registry is None:
        _issue(result, Severity.WARNING, "W145",
               f"Cannot verify '{reference}': the repository index is not loaded", loc)
        return
    if registry.find_file_by_id(str(reference)) is None:
        _issue(result, Severity.ERROR, "E146",
               f"proposed-change names global artifact reference '{reference}', which does not exist",
               loc)


def _check_recorded_edit(fm: dict, result: VerificationResult, loc: str) -> None:
    recorded: Any = fm.get(RECORDED_EDIT)
    if not recorded:
        _issue(result, Severity.ERROR, "E147",
               f"proposed-change is missing required '{RECORDED_EDIT}' field", loc)
        return
    if not isinstance(recorded, dict):
        _issue(result, Severity.ERROR, "E147",
               f"'{RECORDED_EDIT}' is a mapping, not {type(recorded).__name__}", loc)
        return
    try:
        from_mapping(recorded)
    except UnproposableEdit as refused:
        # The union's own refusal, verbatim. It says which field is not editable on which kind, and
        # restating it here would be a second answer to a question that already has one.
        _issue(result, Severity.ERROR, "E147", f"'{RECORDED_EDIT}' is not a recordable edit: {refused}", loc)


def _check_base_revision(fm: dict, result: VerificationResult, loc: str) -> None:
    if not fm.get(BASE_REVISION):
        _issue(result, Severity.ERROR, "E148",
               f"proposed-change is missing required '{BASE_REVISION}' field: without it nothing "
               "can say whether the artifact has moved since the change was written", loc)


def _check_state(fm: dict, result: VerificationResult, loc: str) -> None:
    state = fm.get(PROPOSAL_STATE)
    if state not in STATES:
        _issue(result, Severity.ERROR, "E149",
               f"'{PROPOSAL_STATE}' is {state!r}, not one of {', '.join(STATES)}", loc)
