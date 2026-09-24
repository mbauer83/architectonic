"""The file a shared icon is stored in, written and read here and nowhere else.

`diagram-catalog/icons/ICO@<epoch>.<random>.<slug>.md`: frontmatter describing the icon, then its
render form as a fenced `png-base64` block and, for an SVG upload, the sanitised source as a fenced
`svg` block. Text, so every git workflow the repository has carries it unchanged (D1).

The bytes are immutable once written: replacing a logo is a new icon (D1), so the blocks are never
edited in place and a digest in the frontmatter names them. Checking that the digest matches is the
verifier's; this module only reads and writes the shape, and refuses a file whose shape it cannot
state exactly. Frontmatter keys it does not know are ignored, so a later release may add one.
"""

from __future__ import annotations

import base64
import binascii
import re
import textwrap
from dataclasses import dataclass
from typing import Literal, get_args

import yaml

from src.domain.icons.applicability import Applicability, InvalidApplicabilityError, applicability_from
from src.domain.icons.icon_ref import ICON_STYLES, IconStyle
from src.domain.icons.render_form import SourceFormat
from src.domain.repository.frontmatter import Frontmatter, parse_frontmatter, read_frontmatter

ICON_ARTIFACT_TYPE = "icon"

IconStatus = Literal["active", "retired"]

_SOURCE_FORMATS: tuple[SourceFormat, ...] = get_args(SourceFormat)
_STATUSES: tuple[IconStatus, ...] = get_args(IconStatus)
_PNG_FENCE = "png-base64"
_SVG_FENCE = "svg"
_BLOCK_RE = re.compile(r"^```(png-base64|svg)\n(.*?)\n```$", re.MULTILINE | re.DOTALL)
_BASE64_LINE = 76


@dataclass(frozen=True, slots=True)
class IconMetadata:
    artifact_id: str
    name: str
    source_format: SourceFormat
    width: int
    height: int
    render_digest: str
    attribution: str
    applies_to: Applicability
    default_style: IconStyle
    tags: tuple[str, ...]
    status: IconStatus
    last_updated: str


@dataclass(frozen=True, slots=True)
class IconFile:
    metadata: IconMetadata
    png: bytes
    #: The sanitised SVG an SVG upload was drawn from; None for a raster upload.
    svg_source: str | None = None


@dataclass(frozen=True, slots=True)
class IconFileProblem:
    """Why a file cannot be read as an icon, in words a repair can act on."""

    reason: str


def format_icon_file(icon: IconFile) -> str:
    meta = icon.metadata
    frontmatter = {
        "artifact-id": meta.artifact_id,
        "artifact-type": ICON_ARTIFACT_TYPE,
        "name": meta.name,
        "source-format": meta.source_format,
        "width": meta.width,
        "height": meta.height,
        "render-digest": meta.render_digest,
        "attribution": meta.attribution,
        "applies-to": meta.applies_to.as_list(),
        "default-style": meta.default_style,
        "tags": list(meta.tags),
        "status": meta.status,
        "last-updated": meta.last_updated,
    }
    dumped = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    if not isinstance(dumped, str):
        raise TypeError("yaml.safe_dump returned non-string output")
    encoded = "\n".join(textwrap.wrap(base64.b64encode(icon.png).decode("ascii"), _BASE64_LINE))
    blocks = [f"```{_PNG_FENCE}\n{encoded}\n```"]
    if icon.svg_source is not None:
        blocks.append(f"```{_SVG_FENCE}\n{icon.svg_source.strip()}\n```")
    return f"---\n{dumped.strip()}\n---\n\n" + "\n\n".join(blocks) + "\n"


def read_icon_file(text: str) -> IconFile | IconFileProblem:
    match read_frontmatter(text):
        case Frontmatter(body=body):
            pass
        case _:
            return IconFileProblem("the file has no frontmatter block")
    try:
        metadata = _metadata(parse_frontmatter(text))
    except (_Unreadable, InvalidApplicabilityError) as exc:
        return IconFileProblem(str(exc))
    blocks = {kind: content for kind, content in _BLOCK_RE.findall(body)}
    if _PNG_FENCE not in blocks:
        return IconFileProblem(f"the file has no ```{_PNG_FENCE} block")
    try:
        png = base64.b64decode("".join(blocks[_PNG_FENCE].split()), validate=True)
    except (binascii.Error, ValueError):
        return IconFileProblem(f"the ```{_PNG_FENCE} block is not base64")
    return IconFile(metadata, png, blocks.get(_SVG_FENCE))


class _Unreadable(ValueError):
    pass


def _metadata(fm: dict[str, object]) -> IconMetadata:
    if fm.get("artifact-type") != ICON_ARTIFACT_TYPE:
        raise _Unreadable(f"artifact-type is {fm.get('artifact-type')!r}, not '{ICON_ARTIFACT_TYPE}'")
    return IconMetadata(
        artifact_id=_text(fm, "artifact-id"),
        name=_text(fm, "name"),
        source_format=_one_of(fm, "source-format", _SOURCE_FORMATS),
        width=_positive(fm, "width"),
        height=_positive(fm, "height"),
        render_digest=_text(fm, "render-digest"),
        attribution=_text(fm, "attribution"),
        applies_to=applicability_from(_list(fm, "applies-to")),
        default_style=_one_of(fm, "default-style", ICON_STYLES),
        tags=tuple(str(tag) for tag in _list(fm, "tags")),
        status=_one_of(fm, "status", _STATUSES),
        last_updated=str(fm.get("last-updated") or ""),
    )


def _text(fm: dict[str, object], key: str) -> str:
    value = fm.get(key)
    if not (isinstance(value, str) and value.strip()):
        raise _Unreadable(f"'{key}' must be a non-empty text")
    return value.strip()


def _positive(fm: dict[str, object], key: str) -> int:
    value = fm.get(key)
    if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
        raise _Unreadable(f"'{key}' must be a positive whole number")
    return value


def _list(fm: dict[str, object], key: str) -> list[object]:
    value = fm.get(key, [])
    if not isinstance(value, list):
        raise _Unreadable(f"'{key}' must be a list")
    return value


def _one_of[T: str](fm: dict[str, object], key: str, allowed: tuple[T, ...]) -> T:
    value = fm.get(key)
    for option in allowed:
        if value == option:
            return option
    raise _Unreadable(f"'{key}' must be one of {', '.join(allowed)}, not {value!r}")
