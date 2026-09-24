"""Resolve a reference to a shared icon's picture, through the repository's index.

Only a picture that passes the verifier's own inspection is handed out: an icon file that arrived
through git with bytes the upload path could not have made is reported by the verifier (E362, E363)
and, until it is repaired, drawn as its element's type glyph rather than embedded in a body. The
digest is recomputed from the bytes read, never taken from the file's frontmatter.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.icons.icon_file import IconFile, read_icon_file
from src.domain.icons.icon_record import IconRecord
from src.domain.icons.icon_ref import IconTarget, LocalIcon, SharedIcon
from src.domain.icons.render_form import render_digest
from src.domain.icons.resolved_icon import ResolvedIcon
from src.infrastructure.icons.raster_codec import StoredPngInspector


class IconLookup(Protocol):
    def get_icon(self, artifact_id: str) -> IconRecord | None: ...


class LibraryIconSource:
    """Callable as an `IconSource`; reads each icon file once per instance."""

    def __init__(self, lookup: IconLookup) -> None:
        self._lookup = lookup
        self._inspector = StoredPngInspector()
        self._read: dict[str, ResolvedIcon | None] = {}

    def __call__(self, target: IconTarget) -> ResolvedIcon | None:
        match target:
            case SharedIcon(icon_id=icon_id):
                if icon_id not in self._read:
                    self._read[icon_id] = self._resolved(icon_id)
                return self._read[icon_id]
            case LocalIcon():
                return None  # a diagram's own icons are resolved from its file, not the library

    def _resolved(self, icon_id: str) -> ResolvedIcon | None:
        record = self._lookup.get_icon(icon_id)
        if record is None:
            return None
        try:
            text = record.path.read_text(encoding="utf-8")
        except OSError:
            return None
        match read_icon_file(text):
            case IconFile(metadata=meta, png=png):
                match self._inspector.inspect(png):
                    case (width, height):
                        return ResolvedIcon(png, render_digest(png), width, height, meta.applies_to, meta.default_style)
                    case _:
                        return None
            case _:
                return None
