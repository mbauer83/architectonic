"""Shared display-block parsing and ArchiMate include expansion helpers.

The generated ArchiMate includes are one declaration with two storage forms. A body may keep the
``!include ../_archimate-stereotypes.puml`` marker and have it expanded at render time, or it may
carry the expansion inline so the ``.puml`` renders on its own. Both are permitted (E303 accepts
either), and this module owns reading the syntax in both directions: `ArchimateDeclarations` is the
one reader, and `inject_archimate_includes` is the one entry point — it tells the forms apart and
either expands the marker or restates what is already inlined.

`restated_in` exists because the inline form is a *copy*, and a copy that nothing refreshes is a
second declaration. Nine of this repository's ArchiMate diagrams were still drawing the palette and
the access line style they were authored with, because a body's copy was refreshed only as a side
effect of regenerating the body — so a diagram whose content had not changed never saw an ontology
change at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.config.repo_paths import DIAGRAM_CATALOG
from src.domain.yaml_documents import parse_yaml

#: A `skinparam rectangle<<Type>> { … }` block, whichever file it sits in.
_STEREOTYPE_BLOCK = re.compile(r"skinparam rectangle<<(\w+)>>\s*\{[^}]+\}")
#: A relationship macro definition. The parameter names are the macro's own, so a stale body that
#: spells them differently is still the same declaration and is still restated.
_RELATION_MACRO = re.compile(r"^!define\s+(Rel_\w+)\([^)]*\).*$", re.MULTILINE)
#: A glyph sprite definition, which carries its SVG on the same line.
_SPRITE = re.compile(r"^sprite \$archimate_(\w+)\s.*$", re.MULTILINE)


def parse_archimate_display_block(raw: str) -> dict[str, Any]:

    text = re.sub(r"^```(?:yaml)?\n", "", raw.strip(), count=1)
    text = re.sub(r"\n```$", "", text, count=1)
    try:
        loaded: Any = parse_yaml(text) or {}
    except Exception:  # noqa: BLE001
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass(frozen=True)
class ArchimateDeclarations:
    """What the generated includes declare, indexed by the name each declaration is keyed on."""

    header: str
    stereotype_blocks: Mapping[str, str]
    sprites: Mapping[str, str]
    relation_macros: Mapping[str, str]

    @classmethod
    def from_includes(cls, *, stereotypes: str, glyphs: str, relations: str) -> ArchimateDeclarations:
        first = stereotypes.find("skinparam rectangle<<")
        header = stereotypes if first == -1 else stereotypes[:first].rstrip("\n") + "\n"
        return cls(
            header=header,
            stereotype_blocks={m.group(1): m.group(0) for m in _STEREOTYPE_BLOCK.finditer(stereotypes)},
            sprites={m.group(1): m.group(0) for m in _SPRITE.finditer(glyphs)},
            relation_macros={m.group(1): m.group(0) for m in _RELATION_MACRO.finditer(relations)},
        )

    @classmethod
    def from_repo(cls, repo_root: Path) -> ArchimateDeclarations:
        catalog = repo_root / DIAGRAM_CATALOG

        def read(name: str) -> str:
            try:
                return (catalog / name).read_text(encoding="utf-8")
            except OSError:
                return ""

        return cls.from_includes(
            stereotypes=read("_archimate-stereotypes.puml"),
            glyphs=read("_archimate-glyphs.puml"),
            relations=read("_archimate-relations.puml"),
        )

    def are_inlined_in(self, body: str) -> bool:
        """Whether *body* already carries the expansion rather than the marker.

        The two forms are answered differently and must not be confused: a body with no preamble
        gets one, a body that has one has it restated. Giving the second a marker as well expands a
        whole second preamble beside the one already there — measured, on nine real diagrams.
        """
        return any(
            pattern.search(body) for pattern in (_STEREOTYPE_BLOCK, _SPRITE, _RELATION_MACRO)
        )

    def restated_in(self, body: str) -> str:
        """*body* with every generated declaration it inlines restated as declared here.

        Only what the body already declares is rewritten — never added to, never removed. A body's
        layout, its authored skinparam overrides and its element lines are none of this module's
        business, and a manual-layout diagram must come through unchanged apart from the palette it
        never authored.
        """

        def restate(pattern: re.Pattern[str], known: Mapping[str, str]) -> None:
            nonlocal body
            body = pattern.sub(lambda m: known.get(m.group(1), m.group(0)), body)

        restate(_STEREOTYPE_BLOCK, self.stereotype_blocks)
        restate(_RELATION_MACRO, self.relation_macros)
        restate(_SPRITE, self.sprites)
        return body


#: The markers a body may carry, and the order they are inserted in when it carries none.
_STEREOTYPE_MARKER = "!include ../_archimate-stereotypes.puml"
_GLYPH_MARKER = "!include ../_archimate-glyphs.puml"


def inject_archimate_includes(body: str, repo_root: Path) -> str:
    """Make *body* carry the ontology's current declarations, in whichever form it stores them.

    Three cases, and confusing the first two is what produced two preambles in one body:

    * it already carries the expansion — the declarations are restated in place;
    * it carries the ``!include`` markers — they are replaced by only the skinparam blocks and
      sprites its ``<<stereotype>>`` and ``<$archimate_sprite>`` references need, with every
      relationship macro, so no file-system lookup is needed at render time;
    * it carries neither, which makes it a body the renderer has just produced — it is given the
      markers, then they are expanded as above.
    """
    declarations = ArchimateDeclarations.from_repo(repo_root)
    if declarations.are_inlined_in(body):
        return declarations.restated_in(body)
    for marker in (_STEREOTYPE_MARKER, _GLYPH_MARKER):
        if marker not in body:
            body = re.sub(r"(@startuml(?:\s+\S+)?)\n", rf"\1\n{marker}\n", body, count=1)
    if _STEREOTYPE_MARKER not in body:
        return body

    needed_types = set(re.findall(r"<<(\w+)>>", body))
    needed_sprites = set(re.findall(r"<\$archimate_(\w+)", body))
    already_sprites = set(re.findall(r"^sprite \$archimate_(\w+)", body, re.MULTILINE))
    sprites_to_inject = needed_sprites - already_sprites

    clean_header = _strip_puml_comments(declarations.header)
    parts: list[str] = [clean_header] if clean_header else []
    if declarations.relation_macros:
        parts.append("\n".join(declarations.relation_macros.values()))
    for name in sorted(needed_types):
        if name in declarations.stereotype_blocks:
            parts.append(declarations.stereotype_blocks[name])
    for name in sorted(sprites_to_inject):
        if name in declarations.sprites:
            parts.append(declarations.sprites[name])

    replacement = "\n".join(parts) + "\n"
    result = body.replace(f"{_STEREOTYPE_MARKER}\n", replacement, 1)
    result = result.replace(f"{_GLYPH_MARKER}\n", "")
    return result.replace("!include ../_archimate-relations.puml\n", "")


def _strip_puml_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("'")]
    return "\n".join(lines).strip("\n")
