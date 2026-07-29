"""Tests for the _render_puml preview pipeline.

These tests do NOT require a PlantUML jar or a real engagement repository; they mock
subprocess.run so they run fast and deterministically.  Their job is to verify that the
PUML body written to the temp file before PlantUML is invoked is correct for each diagram
type — particularly that renderer-owned include preparation happens only for diagram types
whose renderer requests it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.infrastructure.rendering.diagram_builder import render_puml_preview

# ── Integration-style pipeline tests (subprocess mocked) ─────────────────────

_ACTIVITY_PUML = """\
@startuml activity-test
title Test

start

:Do something;

stop
@enduml
"""

_ARCHIMATE_PUML = """\
@startuml arch-test
!include ../_archimate-stereotypes.puml
title Test
rectangle "Actor" <<business_actor>> as a1
@enduml
"""


_VERIFIER_MOD = "src.application.verification.artifact_verifier_syntax"
_SETTINGS_MOD = "src.config.settings"


def _captured_puml(tmp_path: Path, puml: str, diagram_type: str | None) -> str:
    """Run render_puml_preview with mocked subprocess; return the PUML written to the temp file."""
    diag_dir = tmp_path / "diagram-catalog" / "diagrams"
    diag_dir.mkdir(parents=True)

    written: list[str] = []

    def _fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        puml_arg = cmd[-1]
        written.append((diag_dir / puml_arg).read_text(encoding="utf-8"))
        out_dir = Path(cmd[cmd.index("-o") + 1])
        (out_dir / "out.png").write_bytes(b"\x89PNG")
        result = MagicMock()
        result.returncode = 0
        return result

    with (
        patch("subprocess.run", side_effect=_fake_run),
        patch(f"{_VERIFIER_MOD}.find_plantuml_jar", return_value=Path("plantuml.jar")),
        patch(f"{_VERIFIER_MOD}.find_graphviz_dot", return_value=None),
        patch(f"{_SETTINGS_MOD}.plantuml_limit_size", return_value=8192),
        patch(f"{_SETTINGS_MOD}.render_dpi", return_value=96),
    ):
        render_puml_preview(puml, tmp_path, diagram_type)

    assert written, "subprocess.run was not called — temp file was not created"
    return written[0]


def test_activity_puml_has_no_archimate_include_injected(tmp_path: Path) -> None:
    body = _captured_puml(tmp_path, _ACTIVITY_PUML, "activity")
    assert "_archimate-stereotypes.puml" not in body
    assert "!include" not in body


def test_activity_puml_preserves_v2_constructs(tmp_path: Path) -> None:
    body = _captured_puml(tmp_path, _ACTIVITY_PUML, "activity")
    assert "start" in body
    assert ":Do something;" in body
    assert "stop" in body


def test_archimate_puml_gets_stereotypes_include_injected(tmp_path: Path) -> None:
    written: list[str] = []
    catalog = tmp_path / "diagram-catalog"
    diag_dir = tmp_path / "diagram-catalog" / "diagrams"
    diag_dir.mkdir(parents=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        """\
!include <archimate/Archimate>
hide stereotype
skinparam rectangle<<business_actor>> {
  BackgroundColor #ffffcc
}
""",
        encoding="utf-8",
    )

    def _fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        puml_arg = cmd[-1]
        written.append((diag_dir / puml_arg).read_text(encoding="utf-8"))
        out_dir = Path(cmd[cmd.index("-o") + 1])
        (out_dir / "out.png").write_bytes(b"\x89PNG")
        r = MagicMock()
        r.returncode = 0
        return r

    with (
        patch("subprocess.run", side_effect=_fake_run),
        patch(f"{_VERIFIER_MOD}.find_plantuml_jar", return_value=Path("plantuml.jar")),
        patch(f"{_VERIFIER_MOD}.find_graphviz_dot", return_value=None),
        patch(f"{_SETTINGS_MOD}.plantuml_limit_size", return_value=8192),
        patch(f"{_SETTINGS_MOD}.render_dpi", return_value=96),
        ):
        render_puml_preview(_ARCHIMATE_PUML, tmp_path, "archimate-business")

    assert written
    assert "_archimate-stereotypes.puml" not in written[0]
    assert "hide stereotype" in written[0]
    assert "skinparam rectangle<<business_actor>>" in written[0]


def test_inline_declaration_gets_correct_stereotypes_and_sprites(tmp_path: Path) -> None:
    """Inline rectangle declarations must trigger stereotype+sprite injection without any _macros.puml."""
    catalog = tmp_path / "diagram-catalog"
    catalog.mkdir(parents=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        """\
hide stereotype
skinparam rectangle<<technology_node>> {
  BackgroundColor #CCFFCC
  BorderColor #2E7D32
}
""",
        encoding="utf-8",
    )
    (catalog / "_archimate-glyphs.puml").write_text(
        'sprite $archimate_technology_node <PUML_PLACEHOLDER>\n',
        encoding="utf-8",
    )

    inline_puml = """\
@startuml inline-test
!include ../_archimate-stereotypes.puml
!include ../_archimate-glyphs.puml
rectangle "<$archimate_technology_node{scale=1.5}> My Node" <<technology_node>> as NOD_AbCd
@enduml
"""
    body = _captured_puml(tmp_path, inline_puml, "archimate-technology")
    assert "_archimate-stereotypes.puml" not in body, "include should have been replaced"
    assert "hide stereotype" in body
    assert "skinparam rectangle<<technology_node>>" in body
    assert "sprite $archimate_technology_node" in body
    assert "_macros.puml" not in body


def test_unknown_diagram_type_leaves_preview_body_unchanged(tmp_path: Path) -> None:
    body = _captured_puml(tmp_path, _ACTIVITY_PUML, None)
    assert "_archimate-stereotypes.puml" not in body
    assert "!include" not in body
