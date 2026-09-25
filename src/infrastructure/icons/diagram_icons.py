"""Icons a diagram holds for itself: ad-hoc uploads kept in its own `diagram-entities.icons` (D11).

An ad-hoc icon belongs to one diagram, so it lives in that diagram's file and every workflow that
carries the diagram carries it — promotion, proposals, rebase, deletion — with nothing of its own.
Statements reference it as `local:<key>`, where the key is its entry's key here.

An entry arrives as an upload — `{name, content_base64, source_format, applies_to?, default_style?}` —
and is stored normalised, as a library icon's picture is: `{name, render-digest, width, height,
applies-to, default-style, png-base64}`. `prepared_local_icons` turns uploads into stored entries,
drops an entry nothing on the diagram references any more, and refuses what it cannot store, with the
reason; it runs on every write before the body is rendered.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping

from src.application.icons.effective_icons import LOCAL_ICONS_KEY, icon_assignments
from src.domain.icons.applicability import InvalidApplicabilityError, applicability_from
from src.domain.icons.icon_ref import ICON_STYLES, IconStyle, IconTarget, LocalIcon, is_local_key
from src.domain.icons.normalised_icon import IconRefused, NormalisedIcon
from src.domain.icons.render_form import SourceFormat, render_digest
from src.domain.icons.resolved_icon import IconSource, ResolvedIcon
from src.infrastructure.icons.normaliser import normalise_upload
from src.infrastructure.icons.raster_codec import StoredPngInspector

#: How many icons one diagram may hold for itself (D11); a logo used more widely belongs in the library.
MAX_LOCAL_ICONS = 8

_SOURCE_FORMATS: dict[object, SourceFormat] = {"svg": "svg", "png": "png", "jpeg": "jpeg", "webp": "webp"}


def prepared_local_icons(diagram_entities: Mapping[str, object]) -> dict[str, object] | IconRefused:
    """*diagram_entities* with its ad-hoc icons stored normalised and unused ones dropped, or why not."""
    raw = diagram_entities.get(LOCAL_ICONS_KEY)
    if raw is None:
        return dict(diagram_entities)
    if not isinstance(raw, Mapping):
        return IconRefused(f"diagram_entities.{LOCAL_ICONS_KEY} must map a key to an icon")
    used = _referenced_local_keys(diagram_entities)
    stored: dict[str, object] = {}
    for key, entry in raw.items():
        if str(key) not in used:
            continue
        match _stored_entry(str(key), entry):
            case IconRefused() as refused:
                return refused
            case dict() as kept:
                stored[str(key)] = kept
    if len(stored) > MAX_LOCAL_ICONS:
        return IconRefused(f"a diagram holds at most {MAX_LOCAL_ICONS} icons of its own; add more to the library")
    prepared = {k: v for k, v in diagram_entities.items() if k != LOCAL_ICONS_KEY}
    return {**prepared, LOCAL_ICONS_KEY: stored} if stored else prepared


class DiagramIconSource:
    """An `IconSource` over a diagram's own icons, then the library for everything else.

    A stored picture is inspected before it is handed out, as a library icon's is, so an entry edited
    by hand to carry bytes the upload path could not have made is drawn as the element's glyph.
    """

    def __init__(self, diagram_entities: Mapping[str, object] | None, library: IconSource | None) -> None:
        raw = (diagram_entities or {}).get(LOCAL_ICONS_KEY)
        self._local = raw if isinstance(raw, Mapping) else {}
        self._library = library
        self._inspector = StoredPngInspector()

    def __call__(self, target: IconTarget) -> ResolvedIcon | None:
        match target:
            case LocalIcon(key=key):
                return self._resolved_local(key)
            case _:
                return self._library(target) if self._library is not None else None

    def _resolved_local(self, key: str) -> ResolvedIcon | None:
        entry = self._local.get(key)
        if not isinstance(entry, Mapping):
            return None
        try:
            png = base64.b64decode(str(entry.get("png-base64", "")), validate=True)
            applies_to = applicability_from(_names(entry.get("applies-to")))
        except (binascii.Error, ValueError, InvalidApplicabilityError):
            return None
        match self._inspector.inspect(png):
            case (width, height):
                style = _style(entry.get("default-style"))
                return ResolvedIcon(png, render_digest(png), width, height, applies_to, style)
            case _:
                return None


def _referenced_local_keys(diagram_entities: Mapping[str, object]) -> frozenset[str]:
    assignments = icon_assignments(diagram_entities)
    refs = [*assignments.by_instance.values(), *assignments.by_name.values()]
    return frozenset(ref.target.key for ref in refs if isinstance(ref.target, LocalIcon))


def _stored_entry(key: str, entry: object) -> dict[str, object] | IconRefused:
    if not is_local_key(key):
        return IconRefused(f"'{key}' is not a local icon key: a lowercase slug of at most 48 characters")
    if not isinstance(entry, Mapping):
        return IconRefused(f"local icon '{key}' must be a mapping")
    if "png-base64" in entry and "content_base64" not in entry:
        return dict(entry)
    return _normalised_entry(key, entry)


def _normalised_entry(key: str, entry: Mapping[str, object]) -> dict[str, object] | IconRefused:
    source_format = _SOURCE_FORMATS.get(entry.get("source_format"))
    if source_format is None:
        return IconRefused(f"local icon '{key}' needs a source_format: one of {', '.join(map(str, _SOURCE_FORMATS))}")
    try:
        content = base64.b64decode(str(entry.get("content_base64", "")), validate=True)
        applies_to = applicability_from(_names(entry.get("applies_to")))
    except (binascii.Error, ValueError, InvalidApplicabilityError) as exc:
        return IconRefused(f"local icon '{key}': {exc}")
    match normalise_upload(content, source_format):
        case IconRefused(reason=reason):
            return IconRefused(f"local icon '{key}': {reason}")
        case NormalisedIcon() as normalised:
            return {
                "name": str(entry.get("name") or key),
                "render-digest": normalised.digest,
                "width": normalised.width,
                "height": normalised.height,
                "applies-to": applies_to.as_list(),
                "default-style": _style(entry.get("default_style")),
                "png-base64": base64.b64encode(normalised.png).decode("ascii"),
            }



def _names(value: object) -> list[object] | None:
    return list(value) if isinstance(value, list) else None


def _style(value: object) -> IconStyle:
    return next((style for style in ICON_STYLES if style == value), "badge")
