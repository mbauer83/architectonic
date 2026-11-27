"""Tests for the _render_puml preview pipeline.

These tests do NOT require a PlantUML jar or a real engagement repository; they stand a
recording PlantUML in for the process's own, so they run fast and deterministically. Their job is
to verify that the PUML body PlantUML is given is correct for each diagram
type — particularly that renderer-owned include preparation happens only for diagram types
whose renderer requests it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.application.plantuml_drawing import Drawn, PictureFormat
from src.infrastructure.rendering.diagram_builder import render_puml_preview

# ── Integration-style pipeline tests (PlantUML stood in for) ─────────────────


class _Recording:
    """A PlantUML that remembers every source it is given and draws a token PNG of each."""

    def __init__(self) -> None:
        self.written: list[str] = []

    def draw(self, source: str, fmt: PictureFormat, *, timeout: float = 60.0) -> Drawn:
        del fmt, timeout
        self.written.append(source)
        return Drawn((b"\x89PNG",))

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
_PLANTUML = "src.infrastructure.rendering.plantuml_runner.PLANTUML"


def _captured_puml(tmp_path: Path, puml: str, diagram_type: str | None) -> str:
    """Run render_puml_preview with PlantUML stood in for; return the PUML it was given."""
    diag_dir = tmp_path / "diagram-catalog" / "diagrams"
    diag_dir.mkdir(parents=True)

    plantuml = _Recording()
    written = plantuml.written

    with (
        patch(_PLANTUML, plantuml),
        patch(f"{_VERIFIER_MOD}.find_plantuml_jar", return_value=Path("plantuml.jar")),
        patch(f"{_VERIFIER_MOD}.find_graphviz_dot", return_value=None),
        patch(f"{_SETTINGS_MOD}.plantuml_limit_size", return_value=8192),
        patch(f"{_SETTINGS_MOD}.render_dpi", return_value=96),
    ):
        render_puml_preview(puml, tmp_path, diagram_type)

    assert written, "PlantUML was not asked to draw"
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
    plantuml = _Recording()
    written = plantuml.written
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

    with (
        patch(_PLANTUML, plantuml),
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
