"""Moving a proposed change through its own lifecycle, in place.

A proposal is stored as an internal artifact, and its state is one frontmatter field. Advancing it is
not an artifact *edit* — nothing a proposal says about the change it carries is altered, and
`proposal-state` is not in the editable vocabulary precisely because an author must not set it by
hand. So this is a narrow operation rather than a route through the general write path.

The field is rewritten in place rather than by re-rendering the file: only the YAML region is
replaced, so both fences, the body and the file's line endings survive a transition that is supposed
to change one word. That is the same treatment the repository upgrade steps give a field they re-pin,
and for the same reason — a rewrite that reformats everything makes the diff useless for review and
risks losing whatever the renderer does not know about.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.application.modeling.proposed_change import PROPOSAL_STATE, STATES, ProposalState
from src.domain.repository.frontmatter import parse_frontmatter, replace_frontmatter_text


class ProposalTransitionRefused(ValueError):
    """A transition that would leave the proposal describing something that did not happen."""


def mark_proposal_state(path: Path, *, artifact_id: str, state: ProposalState) -> bool:
    """Record `state` on the proposal at `path`. Returns whether the file changed."""
    if state not in STATES:
        raise ProposalTransitionRefused(f"{state!r} is not a proposal state; expected one of {', '.join(STATES)}")
    return record_proposal_field(path, artifact_id=artifact_id, field=PROPOSAL_STATE, value=state)


def record_proposal_field(path: Path, *, artifact_id: str, field: str, value: str) -> bool:
    """Record one frontmatter field on the proposal at `path`. Returns whether the file changed.

    Idempotent: a proposal already carrying the value is left byte-identical rather than rewritten,
    so a sweep that runs on every startup does not touch a file per boot — and does not make the
    enterprise repository look dirty to the next status read.

    Two fields move this way and only these two: the lifecycle state, and the base revision a rebase
    has just proven the change against. Both are facts recorded *about* a change rather than part of
    the edit it carries, which is why neither is in the editable vocabulary and why an author cannot
    set either by hand. The mechanism was written twice before it was named once.
    """
    source = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(source)
    if not frontmatter:
        raise ProposalTransitionRefused(f"{artifact_id} has no frontmatter to record {field!r} in")
    if frontmatter.get(field) == value:
        return False

    dumped = yaml.safe_dump({**frontmatter, field: value}, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.safe_dump returned non-string output")
    path.write_text(replace_frontmatter_text(source, dumped.strip()), encoding="utf-8")
    return True
