"""A killed render's scratch file does not survive the next one.

`_render` writes its PlantUML input into the diagram catalog — PlantUML resolves the injected
`!include`s against the including file's directory, so it cannot live elsewhere — and unlinks it in a
`finally`. That covers returning and raising, not being killed: a SIGKILL or an OOM kill orphans the
file where a later `git add -A` can commit it as a diagram, which is how `tmpa6lr5tr0.puml` reached a
commit and surfaced two commits later as an unknown-diagram-type render failure.

`test_no_render_temp_file_is_committed.py` still guards the commit. This guards the accumulation, so
there is nothing left for that mistake to sweep up.

Every file here is this module's own, so exact assertions are fine.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from src.infrastructure.rendering.puml_runtime import (
    _ABANDONED_AFTER_S,
    RENDER_TEMP_GLOB,
    discard_abandoned_render_temp_files,
)


def _aged(path: Path, *, age_s: float) -> Path:
    stamp = time.time() - age_s
    os.utime(path, (stamp, stamp))
    return path


def _scratch_file(directory: Path, *, age_s: float) -> Path:
    """A file named the way the renderer names its scratch files, aged by setting its mtime back.

    Aged *after* the handle closes: closing flushes, which would stamp the mtime back to now.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="tmp", suffix=".puml", dir=directory, delete=False, encoding="utf-8"
    ) as handle:
        handle.write("@startuml\n@enduml\n")
        path = Path(handle.name)
    return _aged(path, age_s=age_s)


def _diagram(directory: Path, name: str, *, age_s: float) -> Path:
    path = directory / name
    path.write_text("@startuml\n@enduml\n", encoding="utf-8")
    return _aged(path, age_s=age_s)


class TestWhatIsSwept:
    def test_an_abandoned_scratch_file_is_removed(self, tmp_path: Path) -> None:
        abandoned = _scratch_file(tmp_path, age_s=_ABANDONED_AFTER_S + 60)

        assert discard_abandoned_render_temp_files(tmp_path) == [abandoned]
        assert not abandoned.exists()

    def test_a_scratch_file_from_a_running_render_is_left_alone(self, tmp_path: Path) -> None:
        """Why there is an age bound at all: renders overlap, and one must not delete another's input
        mid-run. Aged just inside the bound, so the boundary itself is exercised."""
        in_flight = _scratch_file(tmp_path, age_s=_ABANDONED_AFTER_S - 30)

        assert discard_abandoned_render_temp_files(tmp_path) == []
        assert in_flight.exists()

    def test_a_diagram_whose_name_merely_begins_with_the_prefix_is_not_a_scratch_file(
        self, tmp_path: Path
    ) -> None:
        diagram = _diagram(
            tmp_path, "DTY@1782085920.ShZQq.tmp-storage-model.puml", age_s=_ABANDONED_AFTER_S * 10
        )

        assert discard_abandoned_render_temp_files(tmp_path) == []
        assert diagram.exists()

    def test_a_real_diagram_is_never_touched(self, tmp_path: Path) -> None:
        diagram = _diagram(
            tmp_path,
            "ARC@1777452513.d8jG_4.what-we-are-trying-to-achieve.puml",
            age_s=_ABANDONED_AFTER_S * 10,
        )
        _scratch_file(tmp_path, age_s=_ABANDONED_AFTER_S + 60)

        discard_abandoned_render_temp_files(tmp_path)

        assert diagram.exists()
        assert list(tmp_path.glob(RENDER_TEMP_GLOB)) == []

    def test_several_abandoned_files_all_go(self, tmp_path: Path) -> None:
        """Accumulation is the failure being fixed, so more than one must go per call."""
        for _ in range(3):
            _scratch_file(tmp_path, age_s=_ABANDONED_AFTER_S + 60)

        assert len(discard_abandoned_render_temp_files(tmp_path)) == 3
        assert list(tmp_path.glob(RENDER_TEMP_GLOB)) == []


class TestItNeverFailsTheRenderThatCalledIt:
    def test_a_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert discard_abandoned_render_temp_files(tmp_path / "absent") == []

    def test_an_unremovable_file_is_skipped_rather_than_raised(self, tmp_path: Path) -> None:
        """Housekeeping must not turn a working render into a failed one.

        The unwritable *directory* is what blocks the unlink — removing a file is a permission on its
        parent, not on the file.
        """
        locked = tmp_path / "locked"
        locked.mkdir()
        stranded = _scratch_file(locked, age_s=_ABANDONED_AFTER_S + 60)
        locked.chmod(0o500)
        try:
            assert discard_abandoned_render_temp_files(locked) == []
            assert stranded.exists()
        finally:
            locked.chmod(0o700)


def test_a_render_sweeps_before_it_can_return(tmp_path: Path) -> None:
    """The sweep is wired into the render path, not merely available to it.

    Asserted through `render_puml_svg` rather than by reading the source. It needs no PlantUML jar and
    no Java runtime on purpose: the sweep sits ahead of every early return, which is the placement
    being pinned — an environment with no jar still accumulates orphans from whenever it had one.
    """
    from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS
    from src.infrastructure.rendering.puml_runtime import render_puml_svg

    diagram_dir = tmp_path / DIAGRAM_CATALOG / DIAGRAMS
    diagram_dir.mkdir(parents=True)
    abandoned = _scratch_file(diagram_dir, age_s=_ABANDONED_AFTER_S + 60)

    render_puml_svg("@startuml\nA -> B\n@enduml\n", tmp_path, None)

    assert not abandoned.exists()
