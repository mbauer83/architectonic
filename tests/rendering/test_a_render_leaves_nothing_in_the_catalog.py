"""A render, finished or killed while PlantUML runs, leaves nothing in the repository it renders.

A scratch input used to be written into the diagram catalog and removed in a `finally`, which a
killed process never reaches. A body now reaches PlantUML over its pipe and the picture comes back
the same way, so a render writes nothing at all. The killed case is driven for real here: the render
runs in a child process whose `java` is a stand-in that announces itself and waits, and the child's
whole process group is killed while it waits — the moment a SIGKILL or an OOM kill would arrive.

The finished case renders real PlantUML, with the standard-library include a C4 body carries and the
managed-fragment markers a stored ArchiMate body carries, so drawing without a file is shown not to
cost an include.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_syntax import find_plantuml_jar
from src.infrastructure.rendering.puml_runtime import render_puml_bytes

_PROJECT = Path(__file__).resolve().parents[2]
_SELF_MODEL = _PROJECT / "engagements/ENG-ARCH-REPO/architecture-repository"

_needs_plantuml = pytest.mark.skipif(find_plantuml_jar() is None, reason="plantuml.jar is unavailable")


def _everything_under(root: Path) -> set[Path]:
    return {path for path in root.rglob("*")}


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


_RENDER_IN_A_CHILD = """
import sys
from pathlib import Path
from src.infrastructure.rendering.puml_runtime import render_puml_bytes
render_puml_bytes("@startuml\\nrectangle A\\n@enduml\\n", Path(sys.argv[1]), "svg", None)
"""

_STAND_IN_JAVA = """#!/bin/sh
touch "$ARCH_TEST_JAVA_STARTED"
exec sleep 60
"""


@_needs_plantuml
def test_a_render_killed_while_plantuml_runs_leaves_nothing_in_the_repository(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = _everything_under(repo)
    java = tmp_path / "java"
    java.write_text(_STAND_IN_JAVA, encoding="utf-8")
    java.chmod(0o755)
    started = tmp_path / "java-started"
    env = {**os.environ, "ARCH_JAVA": str(java), "ARCH_TEST_JAVA_STARTED": str(started)}

    child = subprocess.Popen(
        [sys.executable, "-c", _RENDER_IN_A_CHILD, str(repo)], cwd=_PROJECT, env=env, start_new_session=True
    )
    try:
        deadline = time.monotonic() + 60
        while not started.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert started.exists(), "the render never reached PlantUML"
    finally:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=30)

    assert child.returncode == -signal.SIGKILL
    assert _everything_under(repo) == before


@_needs_plantuml
def test_a_finished_render_leaves_nothing_and_a_standard_library_include_still_resolves(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = _everything_under(repo)
    body = '@startuml\n!include <C4/C4_Container>\nPerson(reader, "Rosalind")\n@enduml\n'

    svg, media_type, warnings = render_puml_bytes(body, repo, "svg", None)

    assert (media_type, warnings) == ("image/svg+xml", [])
    assert svg is not None and b"Rosalind" in svg and b"&#171;person&#187;" in svg
    assert _everything_under(repo) == before


@_needs_plantuml
@pytest.mark.skipif(not _SELF_MODEL.exists(), reason="the self-model is unavailable")
def test_a_body_with_a_managed_include_marker_renders_and_leaves_the_catalog_as_it_was() -> None:
    """The marker is expanded from the catalog's fragments before PlantUML is given the body."""
    catalog = _SELF_MODEL / "diagram-catalog"
    before = _everything_under(catalog)
    body = (
        "@startuml\n!include ../_archimate-stereotypes.puml\n"
        'rectangle "Ada" <<business-actor>> as ada\n@enduml\n'
    )

    svg, media_type, warnings = render_puml_bytes(body, _SELF_MODEL, "svg", "archimate-business")

    assert (media_type, warnings) == ("image/svg+xml", [])
    assert svg is not None and b"Ada" in svg and b"_archimate-stereotypes" not in svg
    assert _everything_under(catalog) == before
