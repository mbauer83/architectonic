"""The one form an icon is drawn in, and the limits every icon is held to.

Every icon, whatever was uploaded, is stored and embedded as one normalised PNG with alpha, fitted
into `STORED_BOX` — twice the height of the largest drawn icon, and three times as wide so a wordmark
keeps its detail — and at most `MAX_STORED_BYTES` once encoded.
A source is refused before it is decoded when its bytes exceed `MAX_SOURCE_BYTES`, and after its
header is read when either edge exceeds `MAX_SOURCE_EDGE_PX` — the order matters, because the
second check is what stops a small file that declares an enormous canvas.

The digest names the stored bytes, so two uploads that normalise to the same picture are one icon
wherever the digest is compared: promotion, the ad-hoc-to-library hint, a verifier integrity check.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

#: The source formats an upload may be in. SVG is sanitised and rasterised; the others are decoded
#: and re-encoded, so no source byte reaches the stored form unexamined.
SourceFormat = Literal["svg", "png", "jpeg", "webp"]

MAX_SOURCE_BYTES = 1_048_576
MAX_SOURCE_EDGE_PX = 4096
MAX_STORED_BYTES = 32_768


@dataclass(frozen=True, slots=True)
class IconBox:
    """Room for an icon: a height, and how wide it may run. A picture is fitted inside, keeping its shape.

    Fitted rather than scaled by its longer edge, so a wordmark keeps the height a square logo has
    instead of shrinking to a strip, and a tall picture is never taller than the room.
    """

    height_px: int
    max_width_px: int

    def scale_for(self, width: float, height: float) -> float:
        """The factor that fits a *width* × *height* picture inside, as large as it will go."""
        return min(self.height_px / height, self.max_width_px / width)

    def holds(self, width: float, height: float) -> bool:
        return height <= self.height_px and width <= self.max_width_px


#: What every stored icon fits in.
STORED_BOX = IconBox(height_px=128, max_width_px=384)

_DIGEST_SCHEME = "sha256"


def render_digest(stored_png: bytes) -> str:
    """The identity of a stored picture: `sha256:<hex>` over its bytes."""
    return f"{_DIGEST_SCHEME}:{hashlib.sha256(stored_png).hexdigest()}"

