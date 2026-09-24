"""An upload once it has been validated and normalised: what is stored, and what changed on the way."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.icons.render_form import SourceFormat, render_digest


class IconRefusedError(ValueError):
    """An upload that will not be stored, with the reason an uploader can act on."""


@dataclass(frozen=True, slots=True)
class NormalisedIcon:
    source_format: SourceFormat
    png: bytes
    width: int
    height: int
    #: The sanitised source, kept for an SVG upload so a later render form can be derived again.
    svg_source: str | None = None
    #: What normalising removed or changed, e.g. "<script> removed"; warnings, never refusals.
    notes: tuple[str, ...] = ()

    @property
    def digest(self) -> str:
        return render_digest(self.png)
