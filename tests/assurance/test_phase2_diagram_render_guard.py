"""Tests for the G-f assurance render guard in diagram_render.py (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_puml_file(tmp_path: Path, diagram_type: str) -> Path:
    content = (
        f"diagram-type: {diagram_type}\n"
        "---\n"
        "@startuml test\n"
        "component A\n"
        "@enduml\n"
    )
    p = tmp_path / "diagrams" / "test.puml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _mock_parse(diagram_type: str) -> MagicMock:
    parsed = MagicMock()
    parsed.frontmatter = {"diagram-type": diagram_type}
    return parsed


def _assurance_mock() -> MagicMock:
    mock_dt = MagicMock()
    mock_dt.module_class = "assurance"
    return mock_dt


def _architecture_mock() -> MagicMock:
    mock_dt = MagicMock()
    mock_dt.module_class = "architecture"
    return mock_dt


def test_assurance_type_skips_png_render(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram_render import _render_diagram_png

    puml = _make_puml_file(tmp_path, "control-structure")
    warnings: list[str] = []

    with (
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.parse_diagram_file",
            return_value=_mock_parse("control-structure"),
        ),
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.strip_leading_puml_frontmatter",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        patch("src.infrastructure.diagram_type_registry.find_diagram_type", return_value=_assurance_mock()),
    ):
        result = _render_diagram_png(puml, warnings)

    assert result is None
    assert any("G-f" in w or "assurance" in w.lower() for w in warnings)


def test_assurance_type_skips_svg_render(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram_render import _render_diagram_svg

    puml = _make_puml_file(tmp_path, "uca-matrix")
    warnings: list[str] = []

    with (
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.parse_diagram_file",
            return_value=_mock_parse("uca-matrix"),
        ),
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.strip_leading_puml_frontmatter",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        patch("src.infrastructure.diagram_type_registry.find_diagram_type", return_value=_assurance_mock()),
    ):
        result = _render_diagram_svg(puml, warnings)

    assert result is None
    assert any("G-f" in w or "assurance" in w.lower() for w in warnings)


def test_architecture_type_proceeds_past_guard(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram_render import _render_diagram_png

    puml = _make_puml_file(tmp_path, "archimate-business")
    warnings: list[str] = []

    with (
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.parse_diagram_file",
            return_value=_mock_parse("archimate-business"),
        ),
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.strip_leading_puml_frontmatter",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        # Local import inside the function: patch at the source module
        patch("src.infrastructure.diagram_type_registry.find_diagram_type", return_value=_architecture_mock()),
        # Avoid downstream get_diagram_type failure by patching _prepare_diagram_puml_body
        patch(
            "src.infrastructure.write.artifact_write.diagram_render._prepare_diagram_puml_body",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        patch(
            "src.application.verification.artifact_verifier_syntax.find_plantuml_jar",
            return_value=None,
        ),
    ):
        _render_diagram_png(puml, warnings)

    # Guard did not trigger → no G-f warning regardless of render outcome
    assert not any("G-f" in w for w in warnings)


def test_unknown_type_does_not_trigger_guard(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.diagram_render import _render_diagram_png

    puml = _make_puml_file(tmp_path, "unknown-type")
    warnings: list[str] = []

    with (
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.parse_diagram_file",
            return_value=_mock_parse("unknown-type"),
        ),
        patch(
            "src.infrastructure.write.artifact_write.diagram_render.strip_leading_puml_frontmatter",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        # find_diagram_type returns None → guard skips
        patch("src.infrastructure.diagram_type_registry.find_diagram_type", return_value=None),
        patch(
            "src.infrastructure.write.artifact_write.diagram_render._prepare_diagram_puml_body",
            return_value="@startuml test\ncomponent A\n@enduml",
        ),
        patch(
            "src.application.verification.artifact_verifier_syntax.find_plantuml_jar",
            return_value=None,
        ),
    ):
        _render_diagram_png(puml, warnings)

    assert not any("G-f" in w for w in warnings)
