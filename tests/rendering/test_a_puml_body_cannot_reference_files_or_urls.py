"""A PlantUML diagram body cannot make the renderer read a file or fetch a URL, by any spelling, on any path.

Two barriers, each tested on its own, because the defect this guards against was one barrier with a
gap. The body policy used to list what it forbade: `!include_once` and `!include_many` matched no
entry, `<img:…>` and `$sprite="img:…"` were not in the list, the create path never called it, and
PlantUML ran with its default profile — so a submitted `!include_once /path` printed the file into
the rendered SVG. Now the policy names what a body may reference, every write and render path
applies it, and PlantUML itself runs sandboxed, so a spelling the policy misses still reads nothing.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from src.application.puml_directive_policy import UnsafePumlError, find_unsafe_puml_directives
from src.application.verification.artifact_verifier_syntax import (
    PLANTUML_SECURITY_PROFILE,
    check_puml_syntax,
    find_plantuml_jar,
    plantuml_command,
)

ROOT = Path(__file__).resolve().parents[2]
_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


def _body(*lines: str) -> str:
    return "@startuml\n" + "\n".join(lines) + "\nrectangle A\n@enduml\n"


@pytest.mark.parametrize("line", [
    "!include_once /etc/passwd",
    "!include_many /etc/passwd",
    "!INCLUDE_ONCE   /etc/passwd",
    "!importurl http://169.254.169.254/latest/meta-data/",
    'rectangle "<img:/etc/passwd>" as X',
    'rectangle "<img:http://evil.example/x.png>" as X',
    'rectangle "<img src=\\"/etc/passwd\\">" as X',
    'Container(api, "API", "Python", $sprite="img:/etc/passwd")',
    "!$x = %file_exists(\"/etc/shadow\")",
    "!$x = %dirpath()",
])
def test_a_spelling_the_old_list_missed_is_refused(line: str) -> None:
    assert find_unsafe_puml_directives(_body(line)) == [line.strip()]


@pytest.mark.parametrize("line", [
    "!include <C4/C4_Container>",
    "!include ../_archimate-glyphs.puml",
    f'rectangle "<img:{_PNG}>" as X',
    f'rectangle "<img:{_PNG}{{scale=0.5}}>" as X',
    f'Container(api, "API", "Python", $sprite="img:{_PNG}")',
    'rectangle "see [[https://example.org the docs]]" as X',
])
def test_what_a_body_may_contain_is_still_allowed(line: str) -> None:
    assert find_unsafe_puml_directives(_body(line)) == []


def test_every_run_is_sandboxed_through_one_builder(tmp_path: Path) -> None:
    command = plantuml_command(tmp_path / "plantuml.jar", "-tsvg", "x.puml", system_properties=("-DX=1",))

    assert PLANTUML_SECURITY_PROFILE == "SANDBOX"
    assert f"-DPLANTUML_SECURITY_PROFILE={PLANTUML_SECURITY_PROFILE}" in command
    assert command.index("-DX=1") < command.index("-jar") < command.index("-tsvg")


def test_no_code_assembles_a_plantuml_command_outside_the_builder() -> None:
    owner = ROOT / "src" / "application" / "verification" / "artifact_verifier_syntax.py"
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path == owner:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.Constant) and node.value == "-jar" for node in ast.walk(tree)):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"start PlantUML through plantuml_command: {offenders}"


@pytest.mark.skipif(find_plantuml_jar() is None, reason="PlantUML jar not provisioned")
def test_the_sandbox_holds_when_the_policy_is_bypassed(tmp_path: Path) -> None:
    """The policy is not called here at all: this is PlantUML, sandboxed, given the attack."""
    secret = tmp_path / "secret.txt"
    secret.write_text("canary-7f3a9c\n", encoding="utf-8")
    source = tmp_path / "attack.puml"
    source.write_text(_body(f"!include_once {secret}", f'rectangle "<img:{secret}>" as B'), encoding="utf-8")
    jar = find_plantuml_jar()
    assert jar is not None

    subprocess.run(
        plantuml_command(jar, "-tsvg", "-o", str(tmp_path), str(source)),
        capture_output=True, text=True, timeout=120, check=False,
    )

    svg = (tmp_path / "attack.svg").read_text(encoding="utf-8")
    assert "canary-7f3a9c" not in svg


@pytest.mark.skipif(find_plantuml_jar() is None, reason="PlantUML jar not provisioned")
def test_the_bundled_c4_library_still_renders_in_the_sandbox(tmp_path: Path) -> None:
    source = tmp_path / "c4.puml"
    source.write_text(
        '@startuml\n!include <C4/C4_Container>\nContainer(api, "Payments API", "Python")\n@enduml\n',
        encoding="utf-8",
    )
    jar = find_plantuml_jar()
    assert jar is not None

    subprocess.run(
        plantuml_command(jar, "-tsvg", "-o", str(tmp_path), str(source)),
        capture_output=True, text=True, timeout=120, check=True,
    )

    svg = (tmp_path / "c4.svg").read_text(encoding="utf-8")
    # The C4 macro draws a bold label one word per text element.
    assert ">Payments<" in svg and ">API<" in svg


def test_the_verifier_refuses_to_render_a_file_that_arrived_through_git(tmp_path: Path) -> None:
    diagram = tmp_path / "ARC@1.x.pulled.puml"
    diagram.write_text(_body("!include_once /etc/passwd"), encoding="utf-8")

    issues = check_puml_syntax(diagram, str(diagram))

    assert [issue.code for issue in issues] == ["E353"]


def test_the_on_demand_renderer_refuses_the_body(tmp_path: Path) -> None:
    from src.infrastructure.rendering.puml_runtime import render_puml_bytes

    (tmp_path / "diagram-catalog" / "diagrams").mkdir(parents=True)

    data, _, warnings = render_puml_bytes(_body("!include_once /etc/passwd"), tmp_path, "svg", None)

    assert data is None and any("references a file, URL or environment value" in w for w in warnings)


def test_the_on_disk_render_refuses_the_body(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram_render import render_diagram_outputs

    diagram = tmp_path / "diagram.puml"
    diagram.write_text(_body('rectangle "<img:/etc/passwd>" as X'), encoding="utf-8")

    failures = render_diagram_outputs(diagram, [])

    assert failures and "references a file, URL or environment value" in failures[0]


def test_the_create_path_refuses_the_body(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram import _build_from_puml

    with pytest.raises(UnsafePumlError):
        _build_from_puml(
            diagram_type="archimate-application", name="x", repo_root=tmp_path,
            puml=_body("!include_once /etc/passwd"), effective_id=None, auto_include_stereotypes=False,
            entity_ids_used=None, connection_ids_used=None,
        )


@pytest.mark.skipif(find_plantuml_jar() is None, reason="PlantUML jar not provisioned")
def test_a_stored_managed_marker_still_verifies_under_the_sandbox(tmp_path: Path) -> None:
    """The sandbox refuses every file include, the product's own fragments included, so the syntax
    check must inline them first, as every render does — or a correct body reads as broken."""
    from src.infrastructure.verification.adapters import DefaultPumlSyntaxAdapter

    catalog = tmp_path / "diagram-catalog"
    (catalog / "diagrams").mkdir(parents=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        "skinparam rectangle<<goal>> {\n  BackgroundColor #CCCCFF\n}\n", encoding="utf-8",
    )
    diagram = catalog / "diagrams" / "ARC@1.x.marker.puml"
    diagram.write_text(
        '@startuml\n!include ../_archimate-stereotypes.puml\nrectangle "A goal" <<goal>> as G\n@enduml\n',
        encoding="utf-8",
    )

    assert DefaultPumlSyntaxAdapter().check_one(diagram, str(diagram)) == []
    assert DefaultPumlSyntaxAdapter().check_batch([diagram]) == {diagram: []}
    assert "!include ../_archimate-stereotypes.puml" in diagram.read_text(encoding="utf-8")
