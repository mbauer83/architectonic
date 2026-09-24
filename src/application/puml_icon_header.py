"""The block of embedded icon pictures at the top of a PlantUML body: written and read here only.

A body that draws an icon carries the picture itself (D5), so it renders with nothing else present
— in the enterprise before the library is synced, in an export, in any PlantUML. Between
`' arch-icons:begin` and `' arch-icons:end` it holds one `!$ARCH_ICON_<key> = "data:image/png;base64,…"`
per icon the body references, and a declaration shows one with `<img:$ARCH_ICON_<key>{scale=…}>`.

The key is the first twelve hex digits of the picture's render digest: the block is content-addressed,
so one picture used twice is embedded once, a rename moves nothing, and a lost block is rebuilt from
the digests the declarations name. The block is always derived — rebuilt from the references on every
write, never merged — so a hand edit to it lasts until the next write.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping

from src.domain.embedded_image import EmbeddedImage, embedded_image

BLOCK_BEGIN = "' arch-icons:begin"
BLOCK_END = "' arch-icons:end"
ICON_VARIABLE_PREFIX = "ARCH_ICON_"

_KEY_HEX_LENGTH = 12
_KEY_PATTERN = rf"{ICON_VARIABLE_PREFIX}[0-9a-f]{{{_KEY_HEX_LENGTH}}}"
_REFERENCE_RE = re.compile(rf"\$({_KEY_PATTERN})\b")

#: An embedded icon as a declaration shows it, `<img:$ARCH_ICON_…{scale=…}>`. Public so the reader of a
#: declaration's label can tell the picture from the name without spelling the form a second time.
ICON_REFERENCE_PATTERN = rf"<img:\${_KEY_PATTERN}\{{scale=[0-9.]+\}}>"
_ICON_REFERENCE_RE = re.compile(ICON_REFERENCE_PATTERN)
_ASSIGNMENT_RE = re.compile(rf'^\s*!\s*\$({ICON_VARIABLE_PREFIX}\w*)\s*=\s*"?([^"]*)"?\s*$')
_BLOCK_RE = re.compile(rf"^{re.escape(BLOCK_BEGIN)}\n(?:.*\n)*?{re.escape(BLOCK_END)}\n", re.MULTILINE)


def icon_key(render_digest: str) -> str:
    """The variable a picture is embedded under, from its `sha256:<hex>` digest."""
    return ICON_VARIABLE_PREFIX + render_digest.partition(":")[2][:_KEY_HEX_LENGTH]


def icon_reference(key: str, scale: str) -> str:
    """How a declaration shows an embedded icon."""
    return f"<img:${key}{{scale={scale}}}>"


def sprite_reference(key: str, scale: str) -> str:
    """How a macro that takes an image parameter shows an embedded icon — C4's `$sprite="img:…"`."""
    return f"img:${key}{{scale={scale}}}"


def is_icon_reference(text: str) -> bool:
    """Whether *text* is exactly an embedded icon as a declaration shows it."""
    return _ICON_REFERENCE_RE.fullmatch(text) is not None


def referenced_icon_keys(body: str) -> frozenset[str]:
    """Every icon variable the body's declarations use, whether or not the block defines it."""
    return frozenset(_REFERENCE_RE.findall(_BLOCK_RE.sub("", body)))


def embedded_icons(body: str) -> dict[str, EmbeddedImage | None]:
    """What the block assigns to each icon variable: the image, or None where it is not an image.

    Assignments outside the block are included, so a policy reading this sees every place a body
    gives an icon variable a value, not only the one this module writes.
    """
    return {
        name: embedded_image(value)
        for line in body.splitlines()
        if (match := _ASSIGNMENT_RE.match(line)) is not None
        for name, value in [match.groups()]
    }


def assignments_outside_the_block(body: str) -> list[str]:
    """Lines that assign an icon variable anywhere but inside the block this module writes."""
    outside = _BLOCK_RE.sub("", body)
    return [line.strip() for line in outside.splitlines() if _ASSIGNMENT_RE.match(line)]


def with_icon_block(body: str, pictures: Mapping[str, bytes]) -> str:
    """*body* with its block rebuilt for the icons it references that *pictures* holds.

    A body that references none loses its block. The block goes directly after the `@startuml` line,
    ahead of every declaration that can use it.
    """
    without = _BLOCK_RE.sub("", body)
    keys = sorted(referenced_icon_keys(without) & pictures.keys())
    if not keys:
        return without
    block = "\n".join([
        BLOCK_BEGIN,
        *(f'!${key} = "data:image/png;base64,{base64.b64encode(pictures[key]).decode("ascii")}"' for key in keys),
        BLOCK_END,
    ])
    lines = without.split("\n")
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("@startuml")), -1)
    return "\n".join([*lines[: start + 1], block, *lines[start + 1 :]])
