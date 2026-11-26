"""Ephemeral PlantUML and diagram-owned SVG rendering runtime."""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from fnmatch import fnmatch
from pathlib import Path

from src.application.plantuml_pictures import DRAWN, picture_key
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.infrastructure.diagram_type_registry import get_diagram_type
from src.infrastructure.rendering.laid_out_rendering import NoCanvasSizeError, drawn_from_layout, png_like_plantuml
from src.infrastructure.rendering.native_svg import render_native_svg
from src.infrastructure.rendering.plantuml_scratch import plantuml_input
from src.infrastructure.rendering.puml_safety import strip_leading_puml_frontmatter, strip_startuml_name
from src.infrastructure.rendering.svg_to_png import RasteriseFailedError

#: How the scratch files earlier versions wrote *into* the diagram catalog were named. A render now
#: writes its input outside every repository (`plantuml_scratch`), so nothing creates one any more; a
#: catalog can still hold one a killed render of an earlier version left, and the sweep below and the
#: walks that skip such a file recognise it by this name.
_TEMP_PREFIX = tempfile.gettempprefix()
_TEMP_SUFFIX = ".puml"
RENDER_TEMP_GLOB = f"{_TEMP_PREFIX}*{_TEMP_SUFFIX}"


def is_render_scratch(path: Path) -> bool:
    """Whether *path* is one of the renderer's scratch files rather than repository content.

    Anything walking the catalog's ``*.puml`` has to ask: renders overlap with everything else, so a
    scratch file can exist when a walk lists the directory and be gone by the time the walk reads it.
    Asked through the same convention the sweep uses, so a walk cannot drift from what it removes.
    """
    return fnmatch(path.name, RENDER_TEMP_GLOB)


#: How long a scratch file may live before it is assumed abandoned. Comfortably above the 60 s
#: subprocess timeout below, so a render still running is never swept out from under itself — renders
#: do overlap, the pool is bounded but not serial.
_ABANDONED_AFTER_S = 300.0

#: What each requested format's bytes actually are. Stated so a caller setting a `Content-Type` asks
#: the render what it produced rather than assuming the format it asked for — the two differ for a
#: diagram type with a native SVG renderer.
_MEDIA_TYPES = {"svg": "image/svg+xml", "png": "image/png"}


def discard_abandoned_render_temp_files(diagram_dir: Path, *, now: float | None = None) -> list[Path]:
    """Remove scratch files a render of an earlier version left behind, and report what was removed.

    Those renders wrote their input into the diagram catalog and unlinked it in a `finally`, which
    covers returning and raising but not being killed — SIGKILL or an OOM kill skipped it and orphaned
    the file where a later `git add -A` could commit it as if it were a diagram. That happened.

    Best-effort by construction: a file that vanishes underneath us, or that this process may not
    remove, is somebody else's business and must not fail the render that called this.
    """
    reference = now if now is not None else time.time()
    discarded: list[Path] = []
    for candidate in diagram_dir.glob(RENDER_TEMP_GLOB):
        try:
            if reference - candidate.stat().st_mtime <= _ABANDONED_AFTER_S:
                continue
            candidate.unlink()
        except OSError:
            continue
        discarded.append(candidate)
    return discarded


def _prepare_body(puml_body: str, repo_root: Path, diagram_type: str | None) -> str:
    body = strip_leading_puml_frontmatter(puml_body)
    body = strip_startuml_name(body)
    if diagram_type is None:
        return body
    return get_diagram_type(diagram_type).renderer.inject_includes(body, repo_root)


def render_puml_bytes(
    puml_body: str,
    repo_root: Path,
    fmt: str,
    diagram_type: str | None,
    *,
    restyle_prepared: Callable[[str], str] | None = None,
    laid_out: LaidOutDiagram | None = None,
) -> tuple[bytes | None, str, list[str]]:
    """Render *puml_body* and return the image **bytes**, the media type they are, and any warnings.

    The bytes, not a data URL. A data URL is one caller's packaging — the GUI preview's — and while
    that was the only caller it could sit in here harmlessly. It stopped being harmless when a reader
    could download an ad-hoc rendering: a caller needing PNG bytes would either have to decode the
    base64 this function had just encoded, or reach around it into the subprocess. Both are the shape
    of workaround this repository refuses, so the layer that has the bytes hands them over and
    `render_puml_preview` does the encoding it wants.

    The media type is returned rather than inferred from *fmt* because the two can differ: a diagram
    type with a native SVG renderer answers a PNG request with SVG, which was already true and is now
    *sayable*. A caller that sets a `Content-Type` from `fmt` alone would have mislabelled those bytes.

    *laid_out* is the layout a stored diagram states, joined to its picture: the picture is then
    PlantUML's composed again from it, and a PNG is rasterised from that composed SVG.
    """
    from src.application.puml_directive_policy import find_unsafe_puml_directives

    diag_dir = repo_root / DIAGRAM_CATALOG / DIAGRAMS
    if not diag_dir.exists():
        return None, _MEDIA_TYPES[fmt], [f"Diagram directory not found: {diag_dir}"]
    # Before anything can return early: a machine that has switched to native SVG, or that has no
    # PlantUML jar, still carries whatever an earlier version's killed render left behind and is still
    # one `git add -A` away from committing it.
    discard_abandoned_render_temp_files(diag_dir)
    render_body = _prepare_body(puml_body, repo_root, diagram_type)
    # Every on-demand render — previews, reading lenses, bodies that arrived through git — is checked
    # here, on the prepared bytes, which are the bytes PlantUML would be given.
    if offenders := find_unsafe_puml_directives(render_body):
        refusal = f"Render refused: the body references a file, URL or environment value ({offenders[0]})"
        return None, _MEDIA_TYPES[fmt], [refusal]
    # A reading gets its say *after* preparation, and it has to. Preparation restates every stereotype
    # declaration from the ontology — that is the rule keeping one owner for what a kind looks like —
    # so a reading that re-declared a stereotype earlier in the body would have its colour rewritten
    # back. Measured: an appended declaration survives as a block and loses its fill. This is the one
    # point at which a body is final, so it is where a reading that speaks in declarations is applied.
    if restyle_prepared is not None:
        render_body = restyle_prepared(render_body)
    if (native_svg := render_native_svg(render_body, diagram_type)) is not None:
        # Answered in SVG whatever was asked for: this diagram type renders natively and there is no
        # PNG to produce. Saying so in the media type is the whole reason it is returned.
        return native_svg.encode("utf-8"), "image/svg+xml", []

    if laid_out is None:
        return _drawn_by_plantuml(render_body, fmt)
    plantuml_svg, _media_type, warnings = _drawn_by_plantuml(render_body, "svg")
    if plantuml_svg is None:
        return None, _MEDIA_TYPES[fmt], warnings
    svg, composing = drawn_from_layout(plantuml_svg.decode("utf-8"), laid_out)
    if fmt == "svg":
        return svg.encode("utf-8"), _MEDIA_TYPES["svg"], [*warnings, *composing]
    try:
        return png_like_plantuml(svg), _MEDIA_TYPES["png"], [*warnings, *composing]
    except (RasteriseFailedError, NoCanvasSizeError) as exc:
        return None, _MEDIA_TYPES["png"], [f"PNG render failed: {exc}"]


def _render_settings(fmt: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The PlantUML arguments and JVM settings a render in *fmt* is drawn with."""
    from src.config.settings import plantuml_limit_size, render_dpi  # noqa: PLC0415

    return (
        (f"-t{fmt}", *([f"-Sdpi={render_dpi()}"] if fmt == "png" else [])),
        (f"-DPLANTUML_LIMIT_SIZE={plantuml_limit_size()}",),
    )


def plantuml_picture_key(render_body: str, fmt: str) -> str | None:
    """What decides the picture PlantUML draws of a prepared body in *fmt* (`plantuml_pictures`): every
    render of a prepared body keeps and finds its picture by this, so one drawing serves them all."""
    from src.application.verification.artifact_verifier_syntax import (  # noqa: PLC0415
        find_graphviz_dot,
        find_plantuml_jar,
        resolve_java_executable,
    )

    settings, system_properties = _render_settings(fmt)
    return picture_key(
        render_body, *settings, *system_properties, jar=find_plantuml_jar(), dot=find_graphviz_dot(),
        java=resolve_java_executable(),
    )


def _drawn_by_plantuml(render_body: str, fmt: str) -> tuple[bytes | None, str, list[str]]:
    """What PlantUML draws for a prepared body, in *fmt*, with its media type and any warnings."""
    from src.application.verification.artifact_verifier_syntax import (  # noqa: PLC0415
        find_graphviz_dot,
        find_plantuml_jar,
        plantuml_command,
    )

    jar = find_plantuml_jar()
    if jar is None:
        return None, _MEDIA_TYPES[fmt], ["plantuml.jar not found; render skipped"]
    dot = find_graphviz_dot()
    settings, system_properties = _render_settings(fmt)
    key = plantuml_picture_key(render_body, fmt)
    if (drawn := DRAWN.recall(key)) is not None:
        return drawn, _MEDIA_TYPES[fmt], []
    try:
        with plantuml_input(render_body) as scratch, tempfile.TemporaryDirectory() as out_dir:
            env = {**os.environ, "GRAPHVIZ_DOT": str(dot)} if dot else None
            cmd = plantuml_command(
                jar.resolve(), *settings, "-o", out_dir, scratch.name, system_properties=system_properties,
            )
            proc = subprocess.run(
                cmd, cwd=str(scratch.parent), capture_output=True, text=True, timeout=60, env=env
            )
            if proc.returncode != 0:
                return None, _MEDIA_TYPES[fmt], [f"PlantUML render failed: {proc.stderr[:300]}"]
            outputs = list(Path(out_dir).glob(f"*.{fmt}"))
            if not outputs:
                return None, _MEDIA_TYPES[fmt], [f"PlantUML produced no {fmt.upper()} output"]
            drawn = outputs[0].read_bytes()
            DRAWN.keep(key, drawn)
            return drawn, _MEDIA_TYPES[fmt], []
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, _MEDIA_TYPES[fmt], [f"Render error: {exc}"]


def render_puml_preview(
    puml_body: str,
    repo_root: Path,
    diagram_type: str | None = None,
) -> tuple[str | None, list[str]]:
    """Render a diagram to an image data URL for GUI preview.

    The media type comes from the render rather than from the request, so a natively-rendered diagram
    is labelled `image/svg+xml` in its own data URL instead of being announced as a PNG.
    """
    image, media_type, warnings = render_puml_bytes(puml_body, repo_root, "png", diagram_type)
    if image is None:
        return None, warnings
    return f"data:{media_type};base64,{base64.b64encode(image).decode()}", warnings


def render_puml_svg(
    puml_body: str,
    repo_root: Path,
    diagram_type: str | None = None,
    *,
    restyle_prepared: Callable[[str], str] | None = None,
    laid_out: LaidOutDiagram | None = None,
) -> tuple[str | None, list[str]]:
    """Render a diagram to SVG."""
    image, _media_type, warnings = render_puml_bytes(
        puml_body, repo_root, "svg", diagram_type, restyle_prepared=restyle_prepared, laid_out=laid_out
    )
    return (None if image is None else image.decode("utf-8")), warnings
