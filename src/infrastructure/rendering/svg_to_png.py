"""Draw an SVG to PNG with resvg, in a process that has nothing nearby to read.

resvg loads the file an `<image href>` names, relative to the working directory or absolute (measured
on 0.5.0 with resvg 0.48); it does not fetch `file://` or `http://`. Whoever hands a document here is
responsible for what it references — an uploaded icon is sanitised first, a diagram type's own SVG is
generated, never authored — and this module is the second barrier: resvg runs in a child process whose
working directory is an empty temporary directory, in isolated mode (`-I`: no `PYTHONPATH`, no user
site, no script directory on the path) with an environment carrying nothing but the locale, and a
timeout. A relative reference that got this far finds nothing.

The caller states both edges of the picture, so the child never derives an unbounded one from the other.
Two callers: icon uploads (`icons.svg_rasteriser`, which sizes into the icon box) and diagram types that
draw their own SVG (`write.artifact_write.diagram_render`, which sizes like PlantUML's PNG).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

TIMEOUT_SECONDS = 20.0

_CHILD = """
import json, sys
from resvg_py import svg_to_bytes
request = json.load(sys.stdin)
png = svg_to_bytes(
    svg_string=request["svg"], width=request["width"], height=request["height"], background=request["background"],
)
sys.stdout.buffer.write(bytes(png))
"""

#: The locale, and on Windows the one variable an interpreter cannot start without.
_ENVIRONMENT = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"} | {
    name: os.environ[name] for name in ("SYSTEMROOT",) if name in os.environ
}


class RasteriseFailedError(RuntimeError):
    """resvg did not produce a picture: the document failed to render, or took too long."""


def draw_svg_to_png(markup: str, *, width: int, height: int, background: str | None = None) -> bytes:
    """*markup* drawn at *width* × *height* pixels, as PNG bytes.

    Transparent unless *background* names a colour: an icon is laid over whatever it decorates, a
    diagram is a picture on a page and must not read as black text on black in a dark viewer.
    """
    request = json.dumps(
        {"svg": markup, "width": width, "height": height, "background": background}
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="svg-raster-") as empty:
        try:
            completed = subprocess.run(  # a fixed interpreter and program; the SVG goes by stdin
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
