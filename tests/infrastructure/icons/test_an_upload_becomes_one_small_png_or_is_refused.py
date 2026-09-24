"""Every upload is stored as one small PNG, and the refusals say why; nothing outside the upload gets in."""

from __future__ import annotations

import io
import os
import zlib
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from src.domain.icons.normalised_icon import IconRefused, NormalisedIcon
from src.domain.icons.render_form import MAX_SOURCE_BYTES, MAX_STORED_BYTES, STORED_EDGE_PX
from src.infrastructure.icons.normaliser import normalise_upload as _normalise
from src.infrastructure.icons.svg_rasteriser import rasterise_svg

SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
GRADIENT_LOGO = (
    f'<svg {SVG_NS} viewBox="0 0 64 32"><defs><linearGradient id="g" x1="0" x2="1">'
    '<stop offset="0" stop-color="#0078d4"/><stop offset="1" stop-color="#50e6ff"/></linearGradient></defs>'
    '<rect width="64" height="32" fill="url(#g)"/></svg>'
).encode()


def _raster(size: tuple[int, int], fmt: str, colour: tuple[int, int, int, int] = (200, 30, 30, 255), **save) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGBA", size, colour)
    (image.convert("RGB") if fmt == "JPEG" else image).save(buffer, format=fmt, **save)
    return buffer.getvalue()


def normalise_upload(source: bytes, fmt: str) -> NormalisedIcon:
    """The stored icon, for the cases that must produce one; a refusal there fails the test."""
    result = _normalise(source, fmt)  # type: ignore[arg-type]
    assert isinstance(result, NormalisedIcon), result
    return result


def _decoded(png: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png), formats=["PNG"])
    image.load()
    return image


def test_an_svg_with_a_gradient_is_drawn_at_the_stored_size_keeping_its_shape() -> None:
    icon = normalise_upload(GRADIENT_LOGO, "svg")
    image = _decoded(icon.png)

    assert (icon.width, icon.height) == image.size == (STORED_EDGE_PX, STORED_EDGE_PX // 2)
    left, right = image.getpixel((4, 32)), image.getpixel((124, 32))
    assert left != right and left[3] == right[3] == 255  # the gradient survived, opaque
    assert icon.svg_source is not None and "linearGradient" in icon.svg_source
    assert icon.digest.startswith("sha256:")


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_each_raster_format_is_fitted_into_the_stored_form(fmt: str) -> None:
    icon = normalise_upload(_raster((1000, 500), fmt), fmt.lower())

    assert (icon.width, icon.height) == (STORED_EDGE_PX, STORED_EDGE_PX // 2)
    assert len(icon.png) <= MAX_STORED_BYTES and _decoded(icon.png).mode == "RGBA"


def test_a_small_raster_is_not_enlarged() -> None:
    assert normalise_upload(_raster((40, 20), "PNG"), "png").width == 40


def test_metadata_of_the_upload_does_not_survive() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "secret-provenance")
    icon = normalise_upload(_raster((32, 32), "PNG", pnginfo=info), "png")

    assert b"secret-provenance" not in icon.png and not _decoded(icon.png).text


def test_an_animation_keeps_its_first_frame_and_says_so() -> None:
    buffer = io.BytesIO()
    frames = [Image.new("RGBA", (16, 16), c) for c in ((255, 0, 0, 255), (0, 0, 255, 255))]
    frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:])
    icon = normalise_upload(buffer.getvalue(), "webp")

    assert any("first frame" in note for note in icon.notes)


def test_a_detailed_raster_is_reduced_to_fit_the_stored_limit() -> None:
    noise = Image.frombytes("RGBA", (128, 128), os.urandom(128 * 128 * 4))
    buffer = io.BytesIO()
    noise.save(buffer, format="PNG")

    match _normalise(buffer.getvalue(), "png"):
        case IconRefused(reason):
            assert "does not compress" in reason
        case NormalisedIcon(png=png):
            assert len(png) <= MAX_STORED_BYTES


def _declared_canvas(width: int, height: int) -> bytes:
    """A valid PNG header declaring a large canvas, followed by almost no data."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")

    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b"")


@pytest.mark.parametrize(
    ("source", "fmt", "reason"),
    [
        (b"x" * (MAX_SOURCE_BYTES + 1), "png", "at most"),
        (_declared_canvas(60_000, 60_000), "png", "beyond the 4096 px limit"),
        (_declared_canvas(5_000, 5_000), "png", "exceeds the 4096 px limit"),
        (b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n", "png", "not a PNG, JPEG or WebP"),
        (b"GIF89a" + b"\0" * 32, "png", "not a PNG, JPEG or WebP"),
        (b"<svg " + SVG_NS.encode() + b' viewBox="0 0 1 100"/>', "svg", "wider than tall"),
        (b"<svg><path d=", "svg", "well-formed"),
    ],
    ids=["too-large", "declared-bomb", "declared-oversize", "eps", "gif", "thin-svg", "malformed-svg"],
)
def test_a_refusal_names_what_is_wrong(source: bytes, fmt: str, reason: str) -> None:
    result = _normalise(source, fmt)  # type: ignore[arg-type]

    assert isinstance(result, IconRefused) and reason in result.reason, result


RED_MARKER = (255, 0, 0, 255)


def _svg_showing(href: str) -> bytes:
    return f'<svg {SVG_NS} viewBox="0 0 10 10"><image href="{href}" width="10" height="10"/></svg>'.encode()


@pytest.fixture
def a_file_the_upload_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "secret.png"
    marker.write_bytes(_raster((10, 10), "PNG", RED_MARKER))
    return marker


@pytest.mark.parametrize("spelling", ["relative", "absolute", "file-url"])
def test_a_file_an_uploaded_svg_names_never_reaches_the_stored_icon(
    a_file_the_upload_names: Path, spelling: str
) -> None:
    href = {
        "relative": a_file_the_upload_names.name,
        "absolute": str(a_file_the_upload_names),
        "file-url": a_file_the_upload_names.as_uri(),
    }[spelling]
    icon = normalise_upload(_svg_showing(href), "svg")

    assert RED_MARKER not in set(_decoded(icon.png).get_flattened_data())
    assert any("outside the document" in note for note in icon.notes)


def test_the_rasteriser_alone_finds_nothing_beside_the_process_that_started_it(
    a_file_the_upload_names: Path,
) -> None:
    """The second barrier: with the sanitiser bypassed, a relative reference resolves in an empty directory."""
    png = rasterise_svg(_svg_showing(a_file_the_upload_names.name).decode(), 1.0)

    assert RED_MARKER not in set(_decoded(png).get_flattened_data())
