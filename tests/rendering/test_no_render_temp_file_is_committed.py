"""No render temp file is tracked in a diagram catalog.

The renderer writes a `tmp*.puml` beside the diagram it is rendering, so PlantUML's `!include`s
resolve against the catalog, and removes it in a `finally`. A hard kill — SIGKILL, an OOM kill — skips
that cleanup and orphans the file. `test_all_committed_diagrams_render` already tolerates one, by
collecting through `git ls-files` so an *untracked* stray is not mistaken for a diagram.

That defence stops at the word "untracked", and this is the case that walks past it: a `git add -A`
sweeps the orphan into a commit, it becomes tracked, and the render test then correctly tries to render
a frontmatter-less fragment and fails with an unknown-diagram-type error pointing at a file nobody
authored. It happened exactly that way — `tmpa6lr5tr0.puml` was orphaned by an OOM kill, committed by
my own `git add -A`, and surfaced two commits later as a rendering failure.

Cheap to assert, and it fails at the place the mistake was made rather than in the renderer.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from src.infrastructure.rendering.puml_runtime import _TEMP_PREFIX, _TEMP_SUFFIX

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Derived from the renderer's own naming convention rather than restated, so this gate and the sweep
#: in `discard_abandoned_render_temp_files` cannot disagree about what a scratch file looks like. The
#: random middle is `NamedTemporaryFile`'s, hence a pattern rather than a name.
_RENDER_TEMP = re.compile(
    rf"(^|/){re.escape(_TEMP_PREFIX)}[A-Za-z0-9_]{{6,10}}{re.escape(_TEMP_SUFFIX)}$"
)


def _tracked_puml_files() -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", "*.puml"],
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout.decode("utf-8")
    return [rel for rel in listed.split("\0") if rel]


def test_the_scan_sees_the_diagram_catalog_it_means_to() -> None:
    # Without this, a git invocation that returned nothing would report a clean repository.
    tracked = _tracked_puml_files()
    assert len(tracked) > 10, tracked
    assert any("diagram-catalog" in rel for rel in tracked), tracked[:5]


def test_no_render_temp_file_is_tracked() -> None:
    orphans = [rel for rel in _tracked_puml_files() if _RENDER_TEMP.search(rel)]
    assert orphans == [], (
        "these are render temp files, not diagrams — orphaned by a killed render and then committed, "
        f"most likely by a `git add -A`. Remove them with `git rm`: {orphans}"
    )


def test_the_pattern_matches_what_the_renderer_actually_writes() -> None:
    """The guard is only worth having if it recognises the real name shape.

    Asserted against a name `tempfile` produced with the renderer's own prefix and suffix rather than
    one invented here, so the pattern cannot drift away from the thing it is meant to catch.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX) as handle:
        assert _RENDER_TEMP.search(Path(handle.name).name), handle.name

    # And it must not match a real diagram whose name merely begins with "tmp".
    assert not _RENDER_TEMP.search("DTY@1782085920.ShZQq.tmp-storage-model.puml")
