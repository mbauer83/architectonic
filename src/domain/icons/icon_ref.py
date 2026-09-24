"""How a diagram names the icon an element shows, and how it shows it.

Two kinds of icon have two owners (D11), so a reference says which it means:

* `ICO@<epoch>.<random>[.<slug>]` — a shared icon, an artifact of the repository's icon library;
* `local:<key>` — an ad-hoc icon held inside the referring diagram's own file.

A reference may carry a style. Without one, the icon's own default style applies, so choosing an
icon brings its display options with it. A reference is written either as the bare target or as
`{icon: <target>, style: badge|figure}`; both forms read to the same value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, get_args

from src.domain.artifact_id import EMITTED_SLUG_PATTERN, is_entity_id, parse_entity_id, stable_id

#: `badge` sits where the type glyph sits, inside the element; `figure` is the element itself, its
#: label beneath. Which of the two a diagram type can draw is that type's declaration.
IconStyle = Literal["badge", "figure"]

ICON_STYLES: tuple[IconStyle, ...] = get_args(IconStyle)

ICON_ID_PREFIX = "ICO"

LOCAL_PREFIX = "local:"
#: A key is minted the way a slug is (`slugify` of the icon's name), so it is read by the slug grammar,
#: lower-cased and bounded.
_LOCAL_KEY_RE = re.compile(rf"^(?=[a-z0-9-]{{1,48}}$){EMITTED_SLUG_PATTERN}$")


class InvalidIconRefError(ValueError):
    """A value that should name an icon names nothing this module can resolve."""


@dataclass(frozen=True, slots=True)
class SharedIcon:
    """A library icon, by its rename-stable id."""

    icon_id: str

    def spelled(self) -> str:
        return self.icon_id


@dataclass(frozen=True, slots=True)
class LocalIcon:
    """An icon held in the referring diagram's own file, by its key there."""

    key: str

    def spelled(self) -> str:
        return f"{LOCAL_PREFIX}{self.key}"


IconTarget = SharedIcon | LocalIcon


@dataclass(frozen=True, slots=True)
class IconRef:
    target: IconTarget
    #: None takes the icon's own default style.
    style: IconStyle | None = None

    def as_stored(self) -> str | dict[str, str]:
        spelled = self.target.spelled()
        return spelled if self.style is None else {"icon": spelled, "style": self.style}


def _is_local_key(key: str) -> bool:
    return bool(_LOCAL_KEY_RE.match(key))


def icon_target_from(spelled: str) -> IconTarget:
    if spelled.startswith(LOCAL_PREFIX):
        key = spelled.removeprefix(LOCAL_PREFIX)
        if not _is_local_key(key):
            raise InvalidIconRefError(
                f"'{spelled}': a local icon key is a lowercase slug of at most 48 characters"
            )
        return LocalIcon(key)
    if is_entity_id(spelled) and parse_entity_id(spelled).prefix == ICON_ID_PREFIX:
        return SharedIcon(stable_id(spelled))
    raise InvalidIconRefError(f"'{spelled}' names neither a library icon (ICO@…) nor a local one (local:…)")


def icon_ref_from(raw: object) -> IconRef:
    """Read a stored or submitted reference, in either of its two written forms."""
    match raw:
        case str():
            return IconRef(icon_target_from(raw))
        case Mapping():
            return _ref_from_mapping(raw)
        case _:
            raise InvalidIconRefError(f"an icon reference is a string or a mapping, not {type(raw).__name__}")


def _ref_from_mapping(raw: Mapping[object, object]) -> IconRef:
    unknown = set(raw) - {"icon", "style"}
    if unknown:
        raise InvalidIconRefError(f"an icon reference has unknown fields: {sorted(map(str, unknown))}")
    target, style = raw.get("icon"), raw.get("style")
    if not isinstance(target, str):
        raise InvalidIconRefError("an icon reference mapping needs 'icon'")
    return IconRef(icon_target_from(target), _style_from(style))


def _style_from(style: object) -> IconStyle | None:
    if style is None:
        return None
    for known in ICON_STYLES:
        if style == known:
            return known
    raise InvalidIconRefError(f"icon style '{style}' is not one of {', '.join(ICON_STYLES)}")
