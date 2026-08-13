"""A diagram catalog holds what someone authored, and what was rendered from it. Nothing else.

Two ways something else gets in, both of which happened here.

The renderer writes a `tmp*.puml` beside the diagram it is rendering, so PlantUML's `!include`s
resolve against the catalog, and removes it in a `finally`. A hard kill — SIGKILL, an OOM kill — skips
that cleanup and orphans the file. `test_all_committed_diagrams_render` already tolerates one, by
collecting through `git ls-files` so an *untracked* stray is not mistaken for a diagram.

That defence stops at the word "untracked", and this is the case that walks past it: a `git add -A`
sweeps the orphan into a commit, it becomes tracked, and the render test then correctly tries to render
a frontmatter-less fragment and fails with an unknown-diagram-type error pointing at a file nobody
authored. It happened exactly that way — `tmpa6lr5tr0.puml` was orphaned by an OOM kill, committed by
my own `git add -A`, and surfaced two commits later as a rendering failure.

The second is a rendered output whose source is gone. Six such files — three PNG/SVG pairs — were
committed for activity diagrams that `git log --all` shows never had a `.puml` in any commit. A
render is written next to the diagram it came from and removed by nothing, so a diagram deleted or
re-created under another id leaves its picture behind. `artifact_verify` cannot see this: it walks
sources, and an orphaned render is not a source. Nor is it harmless — it is a picture of the model
that the model no longer makes, and anything reading the catalog as a gallery shows it.

Cheap to assert, and both fail at the place the mistake was made rather than in the renderer.
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

#: The same name, whatever PlantUML wrote it as. A render is asked for output too, and that output
#: is named after the scratch input: `.png`, `.svg`, `.cmapx`. Spelling the middle a second time is
#: how the first version of this missed `tmp5lvb_tc2.cmapx` — an underscore is part of the name.
_RENDER_TEMP_ANY = re.compile(
    rf"(^|/){re.escape(_TEMP_PREFIX)}[A-Za-z0-9_]{{6,10}}\.[A-Za-z0-9]+$"
)


def _tracked(*patterns: str) -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", *patterns],
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout.decode("utf-8")
    return [rel for rel in listed.split("\0") if rel]


def _tracked_puml_files() -> list[str]:
    return _tracked("*.puml")


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

    # The output side carries the same name under whatever extension PlantUML was asked for,
    # including the underscore `NamedTemporaryFile` may put in the middle.
    for name in ("tmp5lvb_tc2.cmapx", "tmpmx10a_u2.png", "tmpn4d3rbsd.svg"):
        assert _RENDER_TEMP_ANY.search(name), name
    assert not _RENDER_TEMP_ANY.search("ARC@1780656714.9qoEQO.why-assurance.png")


#: Where a catalog keeps each half. A render is named for the source it came from, which is the whole
#: of the correspondence this asserts.
_SOURCES = "*/diagram-catalog/diagrams/*.puml"
_RENDERS = "*/diagram-catalog/rendered/*"


def test_the_scan_sees_both_halves_of_a_catalog() -> None:
    # Without this, a git invocation returning nothing on either side would report a clean catalog:
    # no renders means no orphans, and no sources means every render is one.
    assert len(_tracked(_SOURCES)) > 10
    assert len(_tracked(_RENDERS)) > 10


def test_every_tracked_render_has_a_source_it_was_rendered_from() -> None:
    sources = {Path(rel).stem for rel in _tracked(_SOURCES)}
    orphans = sorted(
        rel for rel in _tracked(_RENDERS) if Path(rel).stem not in sources
    )

    assert orphans == [], (
        "these are pictures of diagrams that do not exist — left behind when a diagram was deleted "
        "or re-created under another id, and invisible to `artifact_verify`, which walks sources. "
        f"Remove them with `git rm`: {orphans}"
    )


def test_no_render_temp_file_is_tracked_among_the_renders() -> None:
    """The scratch file lands in the catalog it renders *from*, but PlantUML is also asked for
    output, and nothing sweeps the output side at all."""
    strays = sorted(rel for rel in _tracked(_RENDERS) if _RENDER_TEMP_ANY.search(rel))

    assert strays == [], f"render scratch output, not a diagram's picture. Remove with `git rm`: {strays}"
