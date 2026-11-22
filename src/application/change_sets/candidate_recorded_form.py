"""A candidate architecture as plain data, and back: its header, around its change set's own form.

The change set is recorded by `recorded_form` and nested here whole under `changes`, so the two stay
separable on disk as they are in memory: a reader that wants only the operations takes that mapping
and needs nothing from the header. Header keys are hyphenated, as the model's frontmatter is.

Strict on the way in, as the change set's form is, and through the same check.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import yaml

from src.application.change_sets import recorded_form
from src.application.change_sets.candidate_architecture import (
    CandidateArchitecture,
    MalformedCandidateArchitecture,
)
from src.application.change_sets.operations import MalformedChangeSet
from src.domain.yaml_documents import parse_yaml_with_unique_keys

_ID = "id"
_NAME = "name"
_RATIONALE = "rationale"
_STATE = "state"
_PARENT = "parent"
_ANSWERS = "answers"
_SATISFIES = "satisfies"
_SCOPE = "scope"
_CHANGES = "changes"

_REQUIRED = (_ID, _NAME, _STATE, _CHANGES)
_OPTIONAL = (_RATIONALE, _PARENT, _ANSWERS, _SATISFIES, _SCOPE)


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
        _SCOPE: list(candidate.scope),
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
    for key in (_ID, _NAME, _STATE, _RATIONALE, _PARENT):
        if key in recorded and not isinstance(recorded[key], str) and not (key == _PARENT and recorded[key] is None):
            raise MalformedCandidateArchitecture(f"The candidate field {key!r} must be text.")
    for key in (_ANSWERS, _SATISFIES, _SCOPE):
        if key in recorded and not (
            isinstance(recorded[key], list | tuple) and all(isinstance(item, str) for item in recorded[key])
        ):
            raise MalformedCandidateArchitecture(f"The candidate field {key!r} must be a list of references.")
    return CandidateArchitecture(
        id=str(recorded[_ID]),
        name=str(recorded[_NAME]),
        rationale=str(recorded.get(_RATIONALE, "")),
        state=recorded[_STATE],
        changes=recorded_form.from_mapping(recorded[_CHANGES]),
        parent_id=recorded.get(_PARENT),
        answers=tuple(recorded.get(_ANSWERS, ())),
        satisfies=tuple(recorded.get(_SATISFIES, ())),
        scope=tuple(recorded.get(_SCOPE, ())),
    )



def load_candidate(text: str) -> CandidateArchitecture:
    """Read a stored candidate using the repository's strict YAML loader."""
    try:
        raw = parse_yaml_with_unique_keys(text)
        if not isinstance(raw, dict):
            raise MalformedCandidateArchitecture("A candidate file must contain a mapping.")
        return from_mapping(raw)
    except (yaml.YAMLError, TypeError, KeyError, AttributeError, MalformedChangeSet) as exc:
        raise MalformedCandidateArchitecture(f"Cannot read the candidate: {exc}") from exc


def dump_candidate(candidate: CandidateArchitecture) -> str:
    return str(yaml.safe_dump(to_mapping(candidate), sort_keys=False, allow_unicode=True))
