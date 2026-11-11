"""A diagram type that draws its own SVG still has the PNG every diagram is offered as (B88).

GSN draws native SVG, and the render path skipped the PNG for it ("owns scalable SVG notation"). The
download menu offers PNG for every diagram, so a GSN case answered `404 PNG not yet rendered — save the
diagram first`, advice that could never produce one. The PNG is now drawn from the type's own SVG, at
the density PlantUML's PNG has (`render_dpi` over its 96-dpi base).
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from src.config.settings import render_dpi
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-PNG" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def test_a_gsn_case_is_rendered_as_png_beside_its_svg(repo: Path) -> None:
    created = mcp.artifact_create_diagram(
        diagram_type="gsn", name="Argued",
        diagram_entities={
            "nodes": [
                {"node_id": "g1", "name": "The store keeps evidence confidential", "gsn_type": "goal"},
                {"node_id": "sn1", "name": "Negative-leak test suite", "gsn_type": "solution"},
            ],
            "edges": [{"source_id": "g1", "target_id": "sn1", "conn_type": "supported-by"}],
        },
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created

    rendered = list((repo / "diagram-catalog" / "rendered").rglob(f"{created['artifact_id']}.*"))
    by_suffix = {path.suffix: path for path in rendered}
    assert {".svg", ".png"} <= set(by_suffix), rendered

    import re  # noqa: PLC0415 — test-local read of the SVG it is compared with

    view_box = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', by_suffix[".svg"].read_text(encoding="utf-8"))
    assert view_box is not None
    width, height = _png_size(by_suffix[".png"])
    scale = render_dpi() / 96
    assert width == round(float(view_box.group(1)) * scale)
    assert height == round(float(view_box.group(2)) * scale)

    from PIL import Image  # noqa: PLC0415

    with Image.open(by_suffix[".png"]) as picture:
        corner = picture.convert("RGBA").getpixel((0, 0))
    assert corner[3] == 255, "the PNG is transparent; a dark viewer shows its black text on black"
