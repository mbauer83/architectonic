"""Draw a sanitised SVG to PNG with resvg, in a process that has nothing nearby to read.

resvg loads the file an `<image href>` names, relative to the working directory or absolute (measured
on 0.5.0 with resvg 0.48); it does not fetch `file://` or `http://`. The sanitiser is what keeps such
a reference out of the document, and this module is the second barrier: resvg runs in a child
process whose working directory is an empty temporary directory, in isolated mode (`-I`: no
`PYTHONPATH`, no user site, no script directory on the path) with an environment carrying nothing
but the locale, and a timeout. A relative reference that got past the sanitiser finds nothing; an
absolute one is what the sanitiser's tests drive through the whole normalise path.

The child is handed both edges of the picture, so it never derives an unbounded one from the other.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from src.domain.icons.render_form import STORED_EDGE_PX

#: Twice the stored edge, so the raster codec's resampling has detail to work from.
RASTER_EDGE_PX = 2 * STORED_EDGE_PX

TIMEOUT_SECONDS = 20.0

_CHILD = """
import json, sys
from resvg_py import svg_to_bytes
request = json.load(sys.stdin)
png = svg_to_bytes(svg_string=request["svg"], width=request["width"], height=request["height"])
sys.stdout.buffer.write(bytes(png))
"""

#: The locale, and on Windows the one variable an interpreter cannot start without.
_ENVIRONMENT = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"} | {
    name: os.environ[name] for name in ("SYSTEMROOT",) if name in os.environ
}


class RasteriseFailedError(RuntimeError):
    """resvg did not produce a picture: the document failed to render, or took too long."""


def rasterise_svg(markup: str, aspect_ratio: float) -> bytes:
    width, height = _edges(aspect_ratio)
    request = json.dumps({"svg": markup, "width": width, "height": height}).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="icon-raster-") as empty:
        try:
            completed = subprocess.run(  # noqa: S603 — fixed interpreter and program; the SVG goes by stdin
                [sys.executable, "-I", "-c", _CHILD],
                input=request,
                capture_output=True,
                cwd=empty,
                env=_ENVIRONMENT,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RasteriseFailedError(f"the SVG took longer than {TIMEOUT_SECONDS:g} s to draw") from exc
    if completed.returncode != 0 or not completed.stdout:
        reason = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no output"]
        raise RasteriseFailedError(f"the SVG could not be drawn: {reason[0]}")
    return completed.stdout


def _edges(aspect_ratio: float) -> tuple[int, int]:
    if aspect_ratio >= 1:
        return RASTER_EDGE_PX, max(1, round(RASTER_EDGE_PX / aspect_ratio))
    return max(1, round(RASTER_EDGE_PX * aspect_ratio)), RASTER_EDGE_PX
