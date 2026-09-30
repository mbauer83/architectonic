"""Decode an uploaded raster and re-encode it as the one stored form: a small PNG with alpha.

Pillow is told which formats it may open — PNG, JPEG and WebP — and opens nothing else. Left to
itself it identifies dozens, some through external programs (EPS through Ghostscript), and an upload
is not the place to find out which. The header is read before the pixels: an edge beyond
`MAX_SOURCE_EDGE_PX` is refused without decoding, which is what stops a small file that declares an
enormous canvas. Only the pixels are carried into the new image, so no metadata, colour profile or
trailing bytes of the upload survive; an animation contributes its first frame.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from src.application.verification.verifier_ports import PictureProblem
from src.domain.icons.render_form import MAX_SOURCE_EDGE_PX, MAX_STORED_BYTES, STORED_BOX

_OPENABLE = ("PNG", "JPEG", "WEBP")


class RasterRefusedError(ValueError):
    """The upload is not a raster this product will store."""


@dataclass(frozen=True, slots=True)
class StoredRaster:
    png: bytes
    width: int
    height: int
    #: What normalising changed that the uploader may want to know, e.g. "only the first frame kept".
    notes: tuple[str, ...] = ()


def normalise_raster(source: bytes) -> StoredRaster:
    """Fit a PNG, JPEG or WebP into the stored form, or refuse it with the reason."""
    image = _opened(source)
    notes = ("only the first frame of an animation is kept",) if getattr(image, "n_frames", 1) > 1 else ()
    try:
        image.seek(0)
        pixels = image.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise RasterRefusedError(f"the image could not be decoded: {exc}") from exc
    fitted = _fitted(pixels)
    png = _encoded(fitted)
    return StoredRaster(png, fitted.width, fitted.height, notes)


def reencode_embedded(source: bytes) -> bytes | None:
    """A raster embedded in an SVG, re-encoded in the stored form; None when it will not decode."""
    try:
        return normalise_raster(source).png
    except RasterRefusedError:
        return None


def _opened(source: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(source), formats=_OPENABLE)
    except Image.DecompressionBombError as exc:
        # Pillow refuses a canvas far past its own limit while opening, before the check below.
        raise RasterRefusedError(f"the image declares a canvas beyond the {MAX_SOURCE_EDGE_PX} px limit") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise RasterRefusedError("the file is not a PNG, JPEG or WebP image") from exc
    width, height = image.size
    if max(width, height) > MAX_SOURCE_EDGE_PX:
        raise RasterRefusedError(f"{width}×{height} exceeds the {MAX_SOURCE_EDGE_PX} px limit on either edge")
    if min(width, height) < 1:
        raise RasterRefusedError("the image has no pixels")
    return image


def _fitted(image: Image.Image) -> Image.Image:
    scale = min(1.0, STORED_BOX.scale_for(image.width, image.height))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    fitted = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image.copy()
    fitted.info.clear()
    return fitted


def _encoded(image: Image.Image) -> bytes:
    """PNG bytes under the stored limit: full colour when it fits, 256 colours when it must."""
    full = _png(image)
    if len(full) <= MAX_STORED_BYTES:
        return full
    reduced = _png(image.quantize(colors=256, method=Image.Quantize.FASTOCTREE))
    if len(reduced) <= MAX_STORED_BYTES:
        return reduced
    raise RasterRefusedError(
        f"the image does not compress below {MAX_STORED_BYTES // 1024} KB at its stored size; "
        "an icon with fewer colours or less detail will"
    )


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


class StoredPngInspector:
    """The verifier's picture check: whether stored bytes are a PNG the upload path could have made."""

    def inspect(self, png: bytes) -> tuple[int, int] | PictureProblem:
        if len(png) > MAX_STORED_BYTES:
            return PictureProblem(f"{len(png):,} bytes exceeds the {MAX_STORED_BYTES:,}-byte stored limit")
        try:
            image = Image.open(io.BytesIO(png), formats=("PNG",))
            image.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            return PictureProblem("the bytes do not decode as a PNG")
        if not STORED_BOX.holds(*image.size):
            box = f"{STORED_BOX.max_width_px}×{STORED_BOX.height_px}"
            return PictureProblem(f"{image.width}×{image.height} does not fit the {box} px stored size")
        return image.size
