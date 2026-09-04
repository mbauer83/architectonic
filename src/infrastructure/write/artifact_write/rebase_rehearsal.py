"""Driving a rebase rehearsal against a real worktree, so nothing is attempted where it can be seen.

`change_rebase` decides where each change stands, given two capabilities it cannot have: reading the
current enterprise artifact and attempting the replay. This supplies both, against a throwaway
`git worktree` checked out from the enterprise branch.

**The replay is a real write, made somewhere disposable.** Not a simulation of one: a change is the
write call its author would have made, and the only honest way to know whether it still applies is to
make it and let the verifier answer. Anything less re-implements the verifier's judgement, which is
the thing whose answer is wanted. `dry_run=True` is deliberately *not* used — it validates without
writing, so a second change against the same artifact would be judged against content the first one
never produced, and a set is exactly what a rebase rehearses.

The worktree is removed however the rehearsal ends, so the failure path — a set full of conflicts —
leaves the enterprise checkout as it was.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from src.application.modeling.change_rebase import RehearsedRebase, rehearse_rebase
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.infrastructure.git.rehearsal_worktree import rehearsal_worktree

logger = logging.getLogger(__name__)


@contextmanager
def rehearsing(enterprise_root: Path, *, start_point: str) -> Iterator[Path]:
    """A worktree to rehearse in, removed however this ends."""
    with rehearsal_worktree(enterprise_root, start_point=start_point) as rehearsal:
        yield rehearsal.path


def rehearse_against(
    worktree: Path,
    changes: list[tuple[str, ProposalEdit]],
    *,
    read_current: Callable[[Path, str], EntityRecord | DocumentRecord | None],
    apply_edit: Callable[[Path, ProposalEdit], str | None],
) -> RehearsedRebase:
    """Classify `changes` against the artifacts as they stand in `worktree`.

    Both capabilities take the worktree explicitly rather than closing over a repository, because the
    point of the rehearsal is that they read and write *there* — a reader bound to the live index
    would answer from the checkout this is avoiding.
    """
    return rehearse_rebase(
        changes,
        target_of=lambda artifact_id: read_current(worktree, artifact_id),
        replay=lambda edit: apply_edit(worktree, edit),
    )
