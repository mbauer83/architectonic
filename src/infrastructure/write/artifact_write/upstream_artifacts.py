"""What the enterprise repository's *upstream* says, as distinct from what this checkout says.

The two stopped being the same thing the moment a submission could write proposed content locally.
An enterprise checkout on a working branch holds this deployment's own unmerged work — promotions
waiting to be reviewed, and now the replayed effect of every change it has submitted. Reading an
artifact from that checkout answers "what would a reviewer see if they merged us", which is the
wrong question for anything asking whether somebody upstream has *taken up* a change.

Getting that wrong is not a subtle inaccuracy. The integration sweep judges a change integrated when
the enterprise artifact carries its effect, so with the local checkout as its reference every change
read as integrated the moment it was submitted — closed as accepted, terminally and immutably, and
its review branch deleted from the remote while somebody was reading it.

**So the rule is one sentence: whether upstream has taken up a change is asked of `origin/main`.**
Never of the working tree, in any state, so there is no state to get wrong.

The reading goes through a worktree and the ordinary index rather than a second way to parse an
artifact at a ref — the same mechanism a rebase rehearsal uses, for the same reason: the real
parsers, the real records, no fourth reading of the frontmatter fence.

**Unavailable is not "no".** A repository with no upstream ref cannot answer, and the callers here
must treat that as "not known to be integrated" rather than as evidence of anything. Absence of a
remote is equally consistent with a fresh checkout, a fetch that never ran, and a deleted branch.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.infrastructure.git.git_repository_state import UPSTREAM_REF
from src.infrastructure.git.rehearsal_worktree import RehearsalUnavailable

#: Reads one artifact as upstream has it, or None where upstream does not have it.
UpstreamReader = Callable[[str], EntityRecord | DocumentRecord | None]


class UpstreamUnavailable(RuntimeError):
    """Upstream could not be read, so nothing was concluded from it."""


@contextmanager
def upstream_artifacts(enterprise_root: Path) -> Iterator[UpstreamReader]:
    """The artifacts as `origin/main` has them, for the duration of the block.

    Raises `UpstreamUnavailable` rather than falling back to the local checkout: a fallback would
    silently restore exactly the reading this module exists to stop, and would do it on the
    deployments least able to notice — the ones whose remote is unreachable.
    """
    from src.infrastructure.write.artifact_write.rebase_rehearsal import rehearsing  # noqa: PLC0415
    from src.infrastructure.write.artifact_write.rebase_replay import rehearser_for  # noqa: PLC0415

    try:
        with rehearsing(enterprise_root, start_point=UPSTREAM_REF) as worktree:
            with rehearser_for(worktree) as reader:
                yield lambda artifact_id: reader.read_current(worktree, artifact_id)
    except RehearsalUnavailable as unavailable:
        raise UpstreamUnavailable(
            f"Could not read '{UPSTREAM_REF}' in {enterprise_root}: {unavailable}"
        ) from unavailable
