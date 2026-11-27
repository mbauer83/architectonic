"""Which version of its type's stored format a diagram is written in — and whether this product may rewrite it.

A diagram type declares the format version it writes (`diagram_format_version` in its `config.yaml`,
1 where unstated). A diagram states the version it was written in under `diagram-format-version`, 1
where unstated. A product may rewrite a diagram only in a version it knows: one written by a newer
product may hold a construct this one would drop on the way through — the MCP edit replaces
`diagram-entities` whole, a renderer leaves out what it does not draw, an editor rebuilds records
from the fields it knows — so the rewrite is refused rather than silently lossy (C.5b).

The version is stamped only above 1, so the types that have never changed their format write the
files they always wrote; a type stage that adds a construct raises its type's version, and from then
on a product without that construct refuses to rewrite such a diagram instead of losing it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

DIAGRAM_FORMAT_VERSION_KEY: Final = "diagram-format-version"

#: The version of a diagram, or a type, that states none.
FIRST_FORMAT_VERSION: Final = 1


def stated_format_version(frontmatter: Mapping[str, object]) -> int:
    """The format version a diagram's frontmatter states; 1 where it states none (or not an integer)."""
    version = frontmatter.get(DIAGRAM_FORMAT_VERSION_KEY)
    return version if isinstance(version, int) and not isinstance(version, bool) else FIRST_FORMAT_VERSION


def declared_format_version(config: Mapping[str, object]) -> int:
    """The format version a diagram type's `config.yaml` declares it writes; 1 where it declares none."""
    version = config.get("diagram_format_version")
    return version if isinstance(version, int) and not isinstance(version, bool) else FIRST_FORMAT_VERSION


def version_to_stamp(declared: int) -> int | None:
    """What a write records under `diagram-format-version`: the type's version, or nothing for the first."""
    return declared if declared > FIRST_FORMAT_VERSION else None


def newer_format_refusal(frontmatter: Mapping[str, object], declared: int, diagram_type: str) -> str | None:
    """Why this product may not rewrite the diagram, or None where it may."""
    stated = stated_format_version(frontmatter)
    if stated <= declared:
        return None
    return (
        f"This {diagram_type} diagram is written in format version {stated}, and this product writes "
        f"version {declared}: rewriting it could drop what a newer version stored. Update the product "
        "before editing it."
    )
