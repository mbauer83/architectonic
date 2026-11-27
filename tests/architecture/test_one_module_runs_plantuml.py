"""One module runs PlantUML: every render, every syntax check, the doctor's version.

Four modules each started a JVM per diagram with a `subprocess.run` of their own: the preview, the PNG
save, the SVG save and the syntax check. The sandbox flags reached all four only because they shared a
command builder, and the cost — about 0.8 s of JVM start in every render — could only be removed in
four places at once. `plantuml_runner` now owns starting PlantUML, and `plantuml_process` owns the
long-lived process it keeps; nothing else may start one.

A PlantUML command cannot be spelled without `-jar` or the builder, and a pipe-mode one without `-pipe`,
so a second module that runs the jar has to name one of them. These are what is looked for.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources

_RENDERING = SRC / "infrastructure" / "rendering"

#: What each telltale is allowed in, and only there.
_OWNERS: dict[str, frozenset[Path]] = {
    "-jar": frozenset({_RENDERING / "plantuml_runner.py"}),
    "plantuml_command": frozenset({_RENDERING / "plantuml_runner.py"}),
    "-pipe": frozenset({_RENDERING / "plantuml_runner.py", _RENDERING / "plantuml_process.py"}),
}


def _telltales(path: Path) -> set[str]:
    """Which of the telltales *path* spells, as a string literal or as a name."""
    spelled: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        match node:
            case ast.Constant(value=str(text)) if text in _OWNERS:
                spelled.add(text)
            case ast.Name(id=name) | ast.alias(name=name) | ast.Attribute(attr=name) if name in _OWNERS:
                spelled.add(name)
            case ast.FunctionDef(name=name) if name in _OWNERS:
                spelled.add(name)
    return spelled


def test_no_module_but_the_runner_starts_plantuml() -> None:
    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)}: {telltale}"
        for path in python_sources(SRC, TOOLS)
        for telltale in _telltales(path)
        if path not in _OWNERS[telltale]
    )
    assert offenders == [], f"run PlantUML through plantuml_runner.PLANTUML: {offenders}"


def test_the_telltales_are_found_where_they_are_spelled(tmp_path: Path) -> None:
    """The detector catches each spelling it claims to, or the rule above would pass by finding nothing."""
    module = tmp_path / "second_runner.py"
    module.write_text(
        "import subprocess\n"
        "from src.infrastructure.rendering.plantuml_runner import plantuml_command\n"
        "subprocess.run(['java', '-jar', 'plantuml.jar', '-pipe'])\n",
        encoding="utf-8",
    )

    assert _telltales(module) == {"-jar", "-pipe", "plantuml_command"}


def test_the_owners_are_where_the_rule_says() -> None:
    for owners in _OWNERS.values():
        assert all(owner.is_file() for owner in owners), owners
