"""A PNG written as a data URI is read back as the same image: the writer and reader agree."""

from __future__ import annotations

import base64

from src.domain.embedded_image import embedded_image, embedded_png_url
from tests.support.icon_files import png_of


def test_the_written_uri_reads_back_as_the_same_png() -> None:
    png = png_of((10, 20, 30, 255))

    image = embedded_image(embedded_png_url(png))

    assert image is not None and image.subtype == "png" and base64.b64decode(image.payload) == png
