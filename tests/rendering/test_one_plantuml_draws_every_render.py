"""PlantUML runs as one long-lived process per launch, with the sandbox every run had, drawing what a run
per file drew.

Real PlantUML; skipped without plantuml.jar. A runner of the test's own, stopped at the end, so the
process ids asked about are this test's and no other test's.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.application.plantuml_drawing import Drawn
from src.application.verification.artifact_verifier_syntax import (
    check_puml_syntax,
    find_graphviz_dot,
    find_plantuml_jar,
)
from src.config.settings import plantuml_limit_size, render_dpi
from src.infrastructure.rendering.plantuml_runner import PlantUmlLaunch, PlantUmlRunner

pytestmark = pytest.mark.skipif(find_plantuml_jar() is None, reason="plantuml.jar not found")

_BODY = '@startuml\nrectangle "One" as A\nrectangle "Two" as B\nA --> B\n@enduml\n'


@pytest.fixture
def runner() -> Iterator[PlantUmlRunner]:
    own = PlantUmlRunner()
    yield own
    own.stop()


def _drawn(drawing: object) -> Drawn:
    assert isinstance(drawing, Drawn), drawing
    return drawing


def test_two_renders_share_one_process(runner: PlantUmlRunner) -> None:
    _drawn(runner.draw(_BODY, "svg"))
    first = runner.process_ids()
    _drawn(runner.draw(_BODY.replace("One", "Three"), "svg"))

    assert len(first) == 1
    assert runner.process_ids() == first


def test_a_format_is_a_process_of_its_own(runner: PlantUmlRunner) -> None:
    svg, png = _drawn(runner.draw(_BODY, "svg")), _drawn(runner.draw(_BODY, "png"))

    assert svg.picture is not None and svg.picture.startswith(b"<svg")
    assert png.picture is not None and png.picture.startswith(b"\x89PNG")
    assert len(set(runner.process_ids())) == 2  # noqa: PLR2004


@pytest.mark.skipif(not Path("/proc/self/cmdline").exists(), reason="reads the JVM's arguments from /proc")
def test_the_jvm_runs_with_the_sandbox_and_the_render_settings(runner: PlantUmlRunner) -> None:
    _drawn(runner.draw(_BODY, "png"))
    (pid,) = runner.process_ids()

    arguments = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
    environment = Path(f"/proc/{pid}/environ").read_bytes().decode(errors="replace").split("\0")

    jar_at = arguments.index("-jar")
    assert {"-Djava.awt.headless=true", "-DPLANTUML_SECURITY_PROFILE=SANDBOX",
            f"-DPLANTUML_LIMIT_SIZE={plantuml_limit_size()}"} <= set(arguments[:jar_at])
    assert arguments[jar_at + 1] == str(find_plantuml_jar().resolve())  # type: ignore[union-attr]
    assert {"-tpng", f"-Sdpi={render_dpi()}", "-pipe"} <= set(arguments[jar_at + 2:])
    if (dot := find_graphviz_dot()) is not None:
        assert f"GRAPHVIZ_DOT={dot}" in environment


def test_a_launch_states_its_jvm_settings_before_the_jar(tmp_path: Path) -> None:
    launch = PlantUmlLaunch(tmp_path / "plantuml.jar", "java", None, ("-tsvg",), ("-DPLANTUML_LIMIT_SIZE=4096",))

    command = launch.command()

    assert command.index("-DPLANTUML_SECURITY_PROFILE=SANDBOX") < command.index("-jar")
    assert command.index("-DPLANTUML_LIMIT_SIZE=4096") < command.index("-jar") < command.index("-tsvg")
    assert launch.environment() is None


def test_a_refused_body_is_said_to_be_and_the_process_draws_on(runner: PlantUmlRunner) -> None:
    refused = _drawn(runner.draw("@startuml\nA -> \n foo bar(\n@enduml\n", "svg"))
    after = _drawn(runner.draw(_BODY, "svg"))

    assert [refusal.line_from_start for refusal in refused.refusals] == [2]
    assert after.refusals == () and after.picture is not None and b"One" in after.picture


def test_a_source_of_two_diagrams_is_drawn_by_a_plantuml_of_its_own(runner: PlantUmlRunner) -> None:
    drawn = _drawn(runner.draw(_BODY + _BODY.replace("One", "Other"), "svg"))

    assert len(drawn.pictures) == 2  # noqa: PLR2004
    assert runner.process_ids() == ()


def test_the_syntax_check_reports_a_refusal_at_the_line_of_the_file(
    runner: PlantUmlRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
    diagram = tmp_path / "ARC@1.a.broken.puml"
    diagram.write_text(
        "---\nartifact-id: ARC@1.a\nname: broken\n---\n@startuml\nA -> \n foo bar(\n@enduml\n", encoding="utf-8",
    )

    issues = check_puml_syntax(diagram, str(diagram), drawing=runner)

    # Line 7 of the file, as PlantUML numbers a file it reads: the frontmatter counts.
    assert [(issue.code, issue.message) for issue in issues] == [
        ("E350", f"PlantUML: Error line 7 in file: {diagram}"),
    ]


def test_stopping_leaves_no_jvm(runner: PlantUmlRunner) -> None:
    _drawn(runner.draw(_BODY, "svg"))
    (pid,) = runner.process_ids()

    runner.stop()

    assert runner.process_ids() == ()
    with pytest.raises(ProcessLookupError):  # stopped and reaped: the id names no process
        os.kill(pid, 0)
