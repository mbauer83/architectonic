"""A candidate architecture as plain data, and back: its header, around its change set's own form.

The change set is recorded by `recorded_form` and nested here whole under `changes`, so the two stay
separable on disk as they are in memory: a reader that wants only the operations takes that mapping
and needs nothing from the header. Header keys are hyphenated, as the model's frontmatter is.

Strict on the way in, as the change set's form is, and through the same check.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.change_sets import recorded_form
from src.application.change_sets.candidate_architecture import (
    CandidateArchitecture,
    MalformedCandidateArchitecture,
)
from src.application.change_sets.operations import MalformedChangeSet

_ID = "id"
_NAME = "name"
_RATIONALE = "rationale"
_STATE = "state"
_PARENT = "parent"
_ANSWERS = "answers"
_SATISFIES = "satisfies"
_CHANGES = "changes"

_REQUIRED = (_ID, _NAME, _STATE, _CHANGES)
_OPTIONAL = (_RATIONALE, _PARENT, _ANSWERS, _SATISFIES)


def to_mapping(candidate: CandidateArchitecture) -> dict[str, Any]:
    """The recorded form of a candidate. Optional parts that are empty are left out."""
    recorded: dict[str, Any] = {
        _ID: candidate.id,
        _NAME: candidate.name,
        _RATIONALE: candidate.rationale,
        _STATE: candidate.state,
        _PARENT: candidate.parent_id,
        _ANSWERS: list(candidate.answers),
        _SATISFIES: list(candidate.satisfies),
        _CHANGES: recorded_form.to_mapping(candidate.changes),
    }
    return {key: value for key, value in recorded.items() if key in _REQUIRED or value}


def from_mapping(recorded: Mapping[str, Any]) -> CandidateArchitecture:
    """Read a recorded candidate, refusing anything the value or its change set does not admit."""
    try:
        recorded_form.refuse_strangers(
            "a recorded candidate architecture", recorded, _REQUIRED, _OPTIONAL
        )
    except MalformedChangeSet as refusal:
        raise MalformedCandidateArchitecture(str(refusal)) from refusal
    return CandidateArchitecture(
        id=str(recorded[_ID]),
        name=str(recorded[_NAME]),
        rationale=str(recorded.get(_RATIONALE, "")),
        state=recorded[_STATE],
        changes=recorded_form.from_mapping(recorded[_CHANGES]),
        parent_id=recorded.get(_PARENT),
        answers=tuple(recorded.get(_ANSWERS, ())),
        satisfies=tuple(recorded.get(_SATISFIES, ())),
    )

