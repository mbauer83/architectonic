"""A picture an icon reference names, with what decides whether and how an element shows it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.domain.icons.applicability import Applicability
from src.domain.icons.icon_ref import IconStyle, IconTarget


@dataclass(frozen=True, slots=True)
class ResolvedIcon:
    png: bytes
    render_digest: str
    width: int
    height: int
    applies_to: Applicability
    default_style: IconStyle


#: How a reference becomes a picture: the library's, or a diagram's own. None when it names nothing drawable.
IconSource = Callable[[IconTarget], ResolvedIcon | None]
