"""Closing an index takes it out of the shared cache, so the next caller is given a live one.

The caches are process-global and keyed by root: every caller for a root gets the same instance,
and nothing noticed when one holder closed it. The next read then waited on a connection pool that
had been drained and would never be refilled — silently, forever, inside whichever test asked next.
That is what parked the suite at 99% for weeks, and it was diagnosed only by dumping worker stacks
to files, because a hung process forwards nothing.

The mechanism was fixed and had no test. It has one now, because two things lean on it hard: any
caller that opens an index for a scratch checkout and closes it, and the length of time it took to
find the first time.

Both kinds are covered. They are separate caches with separate `close()` implementations, and a fix
applied to one of them is exactly the shape of a defect that comes back.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults


def _repo(root: Path) -> Path:
    (root / "model").mkdir(parents=True, exist_ok=True)
    ensure_arch_repo_defaults(root)
    return root


def test_the_same_root_is_shared_until_it_is_closed(tmp_path: Path) -> None:
    """The sharing is the point of the cache; the test below is about what closing does to it."""
    root = _repo(tmp_path / "engagements" / "ENG-A" / "architecture-repository")

    first = shared_artifact_index(root)
    try:
        assert shared_artifact_index(root) is first
    finally:
        first.close()


def test_a_closed_index_is_replaced_rather_than_handed_out(tmp_path: Path) -> None:
    root = _repo(tmp_path / "engagements" / "ENG-B" / "architecture-repository")
    first = shared_artifact_index(root)
    first.close()

    second = shared_artifact_index(root)

    try:
        assert second is not first
        second.refresh()  # a drained pool would never answer this
    finally:
        second.close()


def test_the_combined_view_is_replaced_too(tmp_path: Path) -> None:
    """Its own cache and its own `close()`, so its own way to hand back a dead one."""
    engagement = _repo(tmp_path / "engagements" / "ENG-C" / "architecture-repository")
    enterprise = _repo(tmp_path / "enterprise-repository")
    first = combined_artifact_index(engagement, enterprise)
    first.close()

    second = combined_artifact_index(engagement, enterprise)

    try:
        assert second is not first
        second.refresh()
    finally:
        second.close()


def test_closing_one_root_leaves_another_alone(tmp_path: Path) -> None:
    """Eviction is by identity, not by clearing the cache: a second root's holders keep theirs."""
    kept = shared_artifact_index(_repo(tmp_path / "engagements" / "ENG-D" / "architecture-repository"))
    closed_root = _repo(tmp_path / "engagements" / "ENG-E" / "architecture-repository")
    shared_artifact_index(closed_root).close()

    try:
        assert shared_artifact_index(kept.repo_mounts[0].root) is kept
    finally:
        kept.close()
