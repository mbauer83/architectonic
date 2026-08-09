"""Regression: a PlantUML run that exits 0 but emits a Java stack trace on stderr
has produced an ERROR IMAGE, not a diagram. The render helpers must surface a
warning, discard the error image, and keep the previous good render.

Guards against graphviz layout crashes (UnparsableGraphvizException) silently
replacing a good render — the error picture then propagates into docs exports.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.write.artifact_write import diagram_render


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

    def _fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        # Simulate PlantUML writing an error image for the temp input and exiting 0
        # with the Java stack trace on stderr.
        tmp_stem = Path(cmd[-1]).stem
        (rendered_dir / f"{tmp_stem}.png").write_bytes(b"ERROR-IMAGE")
        return subprocess.CompletedProcess(
            cmd, 0, stdout="", stderr="Exception java.lang.IllegalStateException"
        )

    monkeypatch.setattr(diagram_render, "find_plantuml_jar", lambda: tmp_path / "plantuml.jar")
    monkeypatch.setattr(diagram_render.subprocess, "run", _fake_run)

    warnings: list[str] = []
    result = diagram_render._render_diagram_png(puml_path, warnings)

    assert result is None
    assert any("error image" in w for w in warnings), warnings
    assert previous.read_bytes() == b"GOOD-RENDER"
    leftovers = [p for p in rendered_dir.glob("*.png") if p != previous]
    assert not leftovers, leftovers


def test_the_image_map_plantuml_writes_beside_a_linked_png_does_not_survive_the_render(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: a diagram carrying links renders a ``.cmapx`` nobody renamed.

    PlantUML names its outputs after the input file, so the render renames
    ``<temp>.png`` onto the diagram's name — but for any diagram with a ``[[link]]``
    it ALSO writes ``<temp>.cmapx``, which no reader consumes and no rename claimed.
    Two of them were found untracked in the catalog after a routine re-render.
    """
    repo_root = tmp_path / "architecture-repository"
    puml_path = _make_diagram(repo_root)
    rendered_dir = repo_root / "diagram-catalog" / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)

    def _fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        tmp_stem = Path(cmd[-1]).stem
        (rendered_dir / f"{tmp_stem}.png").write_bytes(b"PNG")
        (rendered_dir / f"{tmp_stem}.cmapx").write_text("<map/>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(diagram_render, "find_plantuml_jar", lambda: tmp_path / "plantuml.jar")
    monkeypatch.setattr(diagram_render.subprocess, "run", _fake_run)

    result = diagram_render._render_diagram_png(puml_path, [])

    assert result == rendered_dir / f"{puml_path.stem}.png"
    assert result.read_bytes() == b"PNG"
    assert list(rendered_dir.glob("*.cmapx")) == []
