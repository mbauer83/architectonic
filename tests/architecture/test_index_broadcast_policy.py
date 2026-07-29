"""Architectural fitness function: every write-commit path must broadcast.

Multiple independently-cached `ArtifactIndex` singletons can exist for the same physical repo
(one per distinct root-set/scope — see `bootstrap.get_shared_index`). A write committed by calling
`ArtifactIndex.apply_file_changes` directly on just one of them left every sibling singleton
silently stale until a manual `artifact_admin_reindex` — e.g. `artifact_delete_entity` (engagement-
only scope) reporting "not found" for an entity the GUI (engagement+enterprise-combined scope) had
just created. Fixed by routing every write-commit path through `notify_paths_changed`
(`bootstrap.py`), which already applies a change to *every* live registered index whose mounts
overlap it.

This test is the guard against the same class of bug recurring: a call to
`.apply_file_changes(`/`.apply_file_change(` anywhere outside the small, explicitly-reviewed
allowlist below has bypassed the broadcast and is a real, live regression of the fixed bug — the
next such call site should use `notify_paths_changed` instead, not be added to the allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"
_CALL_RE = re.compile(r"\.apply_file_changes?\(")

# Each entry is deliberately narrow and justified — not a blanket per-file exemption:
#   bootstrap.py       — notify_paths_changed's own broadcast loop; this IS the mechanism.
#   service.py         — ArtifactIndex calling its own method on `self` (identity reconciliation
#                         healing that one index's own stale short-id cache from disk); not an
#                         external write event that other cached indices need telling about.
#   bulk/common.py      — local_apply_paths applies changes to a throwaway staging/dry-run temp
#                         directory's own index (`temp_repo_callbacks(staged_root)`), never the
#                         live repo; no other live singleton can share mounts with a fresh temp dir.
_ALLOWED_FILES = frozenset({
    "src/infrastructure/artifact_index/bootstrap.py",
    "src/infrastructure/artifact_index/service.py",
    "src/infrastructure/mcp/artifact_mcp/bulk/common.py",
})


def test_apply_file_changes_is_only_called_from_the_broadcast_allowlist() -> None:
    violations: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        if rel in _ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _CALL_RE.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, (
        "Found a direct ArtifactIndex.apply_file_changes call outside the reviewed allowlist — "
        "this bypasses notify_paths_changed's broadcast to every live cached index sharing the "
        "changed path's repo, reintroducing the cross-scope index-staleness bug "
        "(see tests/infrastructure/artifact_index/test_cross_scope_index_consistency.py). "
        "Use notify_paths_changed(paths) instead, or add this call site to _ALLOWED_FILES here "
        "with a one-line justification for why it's self-contained (e.g. a throwaway temp index) "
        "or is itself part of the broadcast mechanism.\n" + "\n".join(violations)
    )
