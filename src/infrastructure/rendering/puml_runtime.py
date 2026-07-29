"""Ephemeral PlantUML and diagram-owned SVG rendering runtime."""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS
from src.infrastructure.diagram_type_registry import get_diagram_type
from src.infrastructure.rendering.native_svg import render_native_svg
from src.infrastructure.rendering.puml_safety import strip_leading_puml_frontmatter, strip_startuml_name


def _prepare_body(puml_body: str, repo_root: Path, diagram_type: str | None) -> str:
    body = strip_leading_puml_frontmatter(puml_body)
    body = strip_startuml_name(body)
    if diagram_type is None:
        return body
    return get_diagram_type(diagram_type).renderer.inject_includes(body, repo_root)


def _render(
    puml_body: str,
    repo_root: Path,
    fmt: str,
    diagram_type: str | None,
) -> tuple[str | None, list[str]]:
    from src.application.verification.artifact_verifier_syntax import (
        find_graphviz_dot,
        find_plantuml_jar,
        resolve_java_executable,
    )
    from src.config.settings import plantuml_limit_size, render_dpi

    diag_dir = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    if not diag_dir.exists():
        return None, [f"Diagram directory not found: {diag_dir}"]
    render_body = _prepare_body(puml_body, repo_root, diagram_type)
    if (native_svg := render_native_svg(render_body, diagram_type)) is not None:
        if fmt == "svg":
            return native_svg, []
        encoded = base64.b64encode(native_svg.encode()).decode()
        return f"data:image/svg+xml;base64,{encoded}", []

    jar = find_plantuml_jar()
    if jar is None:
        return None, ["plantuml.jar not found; render skipped"]
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".puml", dir=diag_dir, delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(render_body)
            tmp_path = Path(tmp.name)
        with tempfile.TemporaryDirectory() as out_dir:
            env = {**os.environ, "GRAPHVIZ_DOT": str(dot)} if (dot := find_graphviz_dot()) else None
            cmd = [
                resolve_java_executable(),
                "-Djava.awt.headless=true",
                f"-DPLANTUML_LIMIT_SIZE={plantuml_limit_size()}",
                "-jar",
                str(jar.resolve()),
                f"-t{fmt}",
            ]
            if fmt == "png":
                cmd.append(f"-Sdpi={render_dpi()}")
            cmd += ["-o", out_dir, tmp_path.name]
            proc = subprocess.run(
                cmd, cwd=str(diag_dir), capture_output=True, text=True, timeout=60, env=env
            )
            if proc.returncode != 0:
                return None, [f"PlantUML render failed: {proc.stderr[:300]}"]
            outputs = list(Path(out_dir).glob(f"*.{fmt}"))
            if not outputs:
                return None, [f"PlantUML produced no {fmt.upper()} output"]
            if fmt == "png":
                encoded = base64.b64encode(outputs[0].read_bytes()).decode()
                return f"data:image/png;base64,{encoded}", []
            return outputs[0].read_text(encoding="utf-8"), []
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Render error: {exc}"]
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def render_puml_preview(
    puml_body: str,
    repo_root: Path,
    diagram_type: str | None = None,
) -> tuple[str | None, list[str]]:
    """Render a diagram to an image data URL for GUI preview."""
    return _render(puml_body, repo_root, "png", diagram_type)


def render_puml_svg(
    puml_body: str,
    repo_root: Path,
    diagram_type: str | None = None,
) -> tuple[str | None, list[str]]:
    """Render a diagram to SVG."""
    return _render(puml_body, repo_root, "svg", diagram_type)
