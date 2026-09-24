"""An image carried inside text as a `data:` URI — `data:image/<subtype>;base64,<payload>` — read once.

Two policies decide what may be embedded, and both used to spell the URI themselves: the PlantUML
body policy, for which an embedded image is the only image a body may show, and the uploaded-SVG
sanitiser, for which it is the only `<image>` that survives. Each still decides which subtypes it
accepts; what counts as an embedded image is read here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DATA_IMAGE_RE = re.compile(r"^data:image/([a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]*)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EmbeddedImage:
    #: Lower-cased: `png`, `jpeg`, `svg+xml`.
    subtype: str
    #: The base64 text with any whitespace removed; not yet decoded.
    payload: str


def embedded_image(value: str) -> EmbeddedImage | None:
    """The image a `data:image/…;base64,…` URI carries, or None for any other value."""
    match = _DATA_IMAGE_RE.match(value.strip())
    return None if match is None else EmbeddedImage(match.group(1).lower(), "".join(match.group(2).split()))
