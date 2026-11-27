"""Regression: a PlantUML run that exits 0 but emits a Java stack trace on stderr
has produced an ERROR IMAGE, not a diagram. The render helpers must surface a
warning, discard the error image, and keep the previous good render.

Guards against graphviz layout crashes (UnparsableGraphvizException) silently
replacing a good render — the error picture then propagates into docs exports.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.plantuml_drawing import Drawn, PictureFormat
from src.infrastructure.rendering import plantuml_runner
from src.infrastructure.write.artifact_write import diagram_render


class _Answering:
    """A PlantUML that draws every source as *picture*, saying *diagnostics* meanwhile."""

    def __init__(self, picture: bytes, diagnostics: str = "") -> None:
        self._drawn = Drawn((picture,), diagnostics)

    def draw(self, source: str, fmt: PictureFormat, *, timeout: float = 60.0) -> Drawn:
        del source, fmt, timeout
        return self._drawn


def _plantuml_answers(monkeypatch: pytest.MonkeyPatch, picture: bytes, diagnostics: str = "") -> None:
    monkeypatch.setattr(plantuml_runner, "PLANTUML", _Answering(picture, diagnostics))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_diagram(repo_root: Path) -> Path:
    path = repo_root / "diagram-catalog" / "diagrams" / "ARC@1.x.err-render.puml"
    _write(
        path,
        "---\nartifact-id: ARC@1.x.err-render\nartifact-type: diagram\nname: Err\n"
        "version: 0.1.0\nstatus: draft\ndiagram-type: archimate-motivation\n"
        "entity-ids-used: []\nconnection-ids-used: []\nlast-updated: '2026-01-01'\n---\n"
        "@startuml\nrectangle A\n@enduml\n",
    )
    return path


def test_is_error_render_detects_stack_trace() -> None:
    assert diagram_render._is_error_render(
        "Exception java.lang.IllegalStateException\n"
        "net.sourceforge.plantuml.dot.UnparsableGraphvizException: ..."
    )
    assert not diagram_render._is_error_render("")
    assert not diagram_render._is_error_render("some benign notice")


def test_error_image_discarded_and_previous_render_kept(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "architecture-repository"
    puml_path = _make_diagram(repo_root)
    rendered_dir = repo_root / "diagram-catalog" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    previous = rendered_dir / f"{puml_path.stem}.png"
    previous.write_bytes(b"GOOD-RENDER")

    # PlantUML drawing an error image, with the Java stack trace on stderr.
    _plantuml_answers(monkeypatch, b"ERROR-IMAGE", "Exception java.lang.IllegalStateException")

    warnings: list[str] = []
    result = diagram_render._render_diagram_png(puml_path, warnings)

    assert result is None
    assert any("error image" in w for w in warnings), warnings
    assert previous.read_bytes() == b"GOOD-RENDER"
    leftovers = [p for p in rendered_dir.glob("*.png") if p != previous]
    assert not leftovers, leftovers


def test_a_crash_that_says_nothing_on_stderr_is_still_an_error_image(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: the loudest crash class is the silent one.

    An ``EmptySvgException`` out of dot's orthogonal router exits 0, writes nothing to stderr, and
    draws the stack trace into the picture. Reading stderr alone therefore called it a success, and
    a diagram in this repository was written and reported ``valid: true`` with a Java stack trace
    where its component view should have been. The picture is what has to be read.
    """
    repo_root = tmp_path / "architecture-repository"
    puml_path = _make_diagram(repo_root)
    rendered_dir = repo_root / "diagram-catalog" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    previous = rendered_dir / f"{puml_path.stem}.svg"
    previous.write_text("GOOD-RENDER", encoding="utf-8")

    _plantuml_answers(
        monkeypatch,
        b"<svg><text>An error has occurred!</text><text>net.sourceforge.plantuml.svek.EmptySvgException</text></svg>",
    )

    warnings: list[str] = []
    failures: list[str] = []
    result = diagram_render._render_diagram_svg(puml_path, warnings, failures)

    assert result is None
    assert failures, "a crash drawn into the picture must be a failure, not only a warning"
    assert any("error image" in f for f in failures), failures
    assert previous.read_text(encoding="utf-8") == "GOOD-RENDER"


def test_a_healthy_svg_is_not_mistaken_for_an_error_image(tmp_path: Path, monkeypatch) -> None:
    """The marker check must not condemn every diagram that renders."""
    repo_root = tmp_path / "architecture-repository"
    puml_path = _make_diagram(repo_root)
    rendered_dir = repo_root / "diagram-catalog" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)

    _plantuml_answers(monkeypatch, b"<svg><rect/></svg>")

    failures: list[str] = []
    result = diagram_render._render_diagram_svg(puml_path, [], failures)

    assert result == rendered_dir / f"{puml_path.stem}.svg"
    assert not failures


def test_a_png_render_writes_the_diagrams_own_file_and_nothing_else(tmp_path: Path, monkeypatch) -> None:
    """The picture comes back over PlantUML's pipe and is written under the diagram's name — no
    temporary name to rename, and none of the by-products (a ``.cmapx`` image map for a linked diagram)
    a render into the catalog directory used to leave there."""
    repo_root = tmp_path / "architecture-repository"
    puml_path = _make_diagram(repo_root)
    rendered_dir = repo_root / "diagram-catalog" / "rendered"
    _plantuml_answers(monkeypatch, b"PNG")

    result = diagram_render._render_diagram_png(puml_path, [])

    assert result == rendered_dir / f"{puml_path.stem}.png"
    assert result.read_bytes() == b"PNG"
    assert sorted(path.name for path in rendered_dir.iterdir()) == [f"{puml_path.stem}.png"]
