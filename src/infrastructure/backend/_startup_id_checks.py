"""Fail-closed startup checks for stable-id collisions (WS2/WS9)."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports import ReadableArtifactStore

logger = logging.getLogger(__name__)


def assert_no_duplicate_short_ids(index: "ReadableArtifactStore") -> None:
    """Fail closed if a stable id maps to >1 distinct file within one mount."""
    duplicates = index.scan_duplicate_short_ids()
    if duplicates:
        detail = "\n".join(f"  {short}: {[str(p) for p in paths]}" for short, paths in sorted(duplicates.items()))
        logger.error(
            "Startup aborted — stable id(s) map to multiple files in one mount "
            "(rename/shadowing hazard); resolve the duplicates and restart:\n%s",
            detail,
        )
        sys.exit(1)


def assert_no_cross_repo_id_collisions(index: "ReadableArtifactStore") -> None:
    """Fail closed if the same full artifact_id exists in both engagement and enterprise.

    `scan_duplicate_short_ids` cannot see this case (see `CombinedArtifactView
    .cross_repo_duplicate_ids`'s docstring) — that state is never legitimate outside
    promotion's transient copy-then-unlink window, and no promotion is ever in flight
    at startup.
    """
    from src.infrastructure.artifact_index.combined_index import CombinedArtifactView

    if not isinstance(index, CombinedArtifactView):
        return
    collisions = index.cross_repo_duplicate_ids()
    if collisions:
        detail = "\n".join(f"  {aid}" for aid in sorted(collisions))
        logger.error(
            "Startup aborted — artifact id(s) exist in both the engagement and enterprise "
            "repos outside a promotion in progress; resolve the collision and restart:\n%s",
            detail,
        )
        sys.exit(1)
