"""The one form an icon is drawn in, and the limits every icon is held to.

Every icon, whatever was uploaded, is stored and embedded as one normalised PNG with alpha: at most
`STORED_EDGE_PX` on its longer edge (twice a 64 px display size) and `MAX_STORED_BYTES` once encoded.
A source is refused before it is decoded when its bytes exceed `MAX_SOURCE_BYTES`, and after its
header is read when either edge exceeds `MAX_SOURCE_EDGE_PX` — the order matters, because the
second check is what stops a small file that declares an enormous canvas.

The digest names the stored bytes, so two uploads that normalise to the same picture are one icon
wherever the digest is compared: promotion, the ad-hoc-to-library hint, a verifier integrity check.
"""

from __future__ import annotations

import hashlib
from typing import Literal

#: The source formats an upload may be in. SVG is sanitised and rasterised; the others are decoded
#: and re-encoded, so no source byte reaches the stored form unexamined.
SourceFormat = Literal["svg", "png", "jpeg", "webp"]

SOURCE_FORMATS: tuple[SourceFormat, ...] = ("svg", "png", "jpeg", "webp")

MAX_SOURCE_BYTES = 1_048_576
MAX_SOURCE_EDGE_PX = 4096
STORED_EDGE_PX = 128
MAX_STORED_BYTES = 32_768

#: How many icons one diagram may carry inside its own file (D11). Shared icons do not count.
MAX_AD_HOC_ICONS_PER_DIAGRAM = 8

_DIGEST_SCHEME = "sha256"


def render_digest(stored_png: bytes) -> str:
    """The identity of a stored picture: `sha256:<hex>` over its bytes."""
    return f"{_DIGEST_SCHEME}:{hashlib.sha256(stored_png).hexdigest()}"


def is_render_digest(value: str) -> bool:
    scheme, _, hex_part = value.partition(":")
    return scheme == _DIGEST_SCHEME and len(hex_part) == 64 and all(c in "0123456789abcdef" for c in hex_part)
