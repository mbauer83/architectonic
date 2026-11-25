"""`get-diagram-runtime` leaves the installed Graphviz and nothing else, and git ignores all of it.

A source build left `tools/_graphviz-src/` (about 160 MB) and the downloaded archive (21 MB) behind,
and none of the three paths was ignored, so a checkout showed them as untracked after the documented
setup step.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.bootstrap.get_diagram_runtime import (
    GRAPHVIZ_INSTALL_DIRNAME,
    build_intermediates,
    discard_build_intermediates,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_a_successful_build_discards_its_archive_and_source_tree(tmp_path: Path) -> None:
    archive, source = build_intermediates(tmp_path)
    archive.write_bytes(b"xz")
    (source / "graphviz-x").mkdir(parents=True)
    (source / "graphviz-x" / "Makefile").write_text("all:\n")
    installed = tmp_path / GRAPHVIZ_INSTALL_DIRNAME / "bin"
    installed.mkdir(parents=True)

    discard_build_intermediates(tmp_path)

    assert not archive.exists() and not source.exists()
    assert installed.is_dir()


def test_git_ignores_every_path_the_build_writes() -> None:
    archive, source = build_intermediates(Path("tools"))
    paths = [str(archive), f"{source}/graphviz-x/configure", f"tools/{GRAPHVIZ_INSTALL_DIRNAME}/bin/dot"]

    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *paths], cwd=_ROOT, capture_output=True, text=True, check=False,
    )

    assert sorted(result.stdout.split()) == sorted(paths)
