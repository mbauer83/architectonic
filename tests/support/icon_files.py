"""Real icon files for tests: normalised through the product's own path and written by its own writer."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from src.domain.icons.applicability import applicability_from
from src.domain.icons.icon_file import IconFile, IconMetadata, format_icon_file
from src.domain.icons.render_form import render_digest


def png_of(colour: tuple[int, int, int, int] = (0, 120, 212, 255), size: tuple[int, int] = (32, 32)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def icon_file(
    artifact_id: str = "ICO@1790000000.aks001.azure-kubernetes-service",
    *,
    name: str = "Azure Kubernetes Service",
    applies_to: tuple[str, ...] = (),
    png: bytes | None = None,
    status: str = "active",
) -> IconFile:
    picture = png if png is not None else png_of()
    width, height = Image.open(io.BytesIO(picture)).size
    metadata = IconMetadata(
        artifact_id=artifact_id, name=name, source_format="png", width=width, height=height,
        render_digest=render_digest(picture), attribution="Test fixture, no third-party mark",
        applies_to=applicability_from(applies_to), default_style="badge", tags=("test",),
        status=status,  # type: ignore[arg-type]
        last_updated="2026-09-24T12:00:00Z",
    )
    return IconFile(metadata, picture)


def write_icon(repo_root: Path, icon: IconFile | None = None) -> Path:
    icon = icon or icon_file()
    path = repo_root / "diagram-catalog" / "icons" / f"{icon.metadata.artifact_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_icon_file(icon), encoding="utf-8")
    return path
