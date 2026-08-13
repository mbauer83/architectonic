"""What it means for a line of PUML to declare an alias. One reading, for every caller.

There were **five**, and they disagreed. The disagreement was the defect: the write path derived
`entity-ids-used` with one of them and the verifier resolved drawn aliases with another, so a body
could draw an entity the writer refused to list — and E315 then correctly objected to an alias the
writer had dropped. Measured on 0.5.2: a body drawing `function → junction → function` with the
junction declared `circle " " as JNA_x #252327` lost the junction from `entity-ids-used` *and* both
its connections from `connection-ids-used`, then failed E315; the same body without the colour
verified clean. Not a junction problem — a coloured `rectangle` failed identically, with E317 on top,
which is why it presented as a stale index.

Each of the five knew something the others did not, so this is the union rather than a pick:

* **Anything may follow the alias.** `as X #252327`, `as X #E6F3FF {`, `as X <<Note>>`. Three of the
  five anchored the alias to the end of the line, which is what a trailing colour defeats — and the
  product's own renderer emits one for every specialised entity (`entity_declaration`'s
  `color_suffix`), so this was never only about hand-authored bodies.
* **Quoted text is not code.** A label may contain the word "as" — `"AI-Assisted Development as
  Dominant Production Mode"` — and one caller alone stripped quotes before looking, so the other four
  read `Dominant` as an alias.
* **A hyphen is part of an alias.** Two of the five used `\\w+`, which silently truncated one.
* **Whether the line opens a block is a separate question**, and the caller's. Containment parsing
  needs it, alias collection does not, and encoding it as two regexes is what made "leaf" mean "the
  line ends after the alias" — a colour then made an element neither leaf nor container.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `… as ALIAS` followed by anything but a further alias. The trailing group is deliberately
#: unconstrained: PlantUML permits colours, sprites, stereotypes and sizing hints after the alias,
#: and an allowlist of decorations is the same bet the end-anchored readings lost.
_DECLARATION = re.compile(r"\bas\s+(?P<alias>[A-Za-z0-9_-]+)\b")

#: A quoted label, replaced before the search so its prose cannot look like a declaration.
_QUOTED = re.compile(r'"[^"]*"')

#: `MacroName(ALIAS)` or `MacroName(ALIAS, "label", …)` — some renderers put the alias first rather
#: than after `as`. A **quoted** second argument, or none at all, is what distinguishes a
#: declaration from a relation: `Rel_Realization(REQ_kOU3al, OUT_620dTh, "")` names two aliases and
#: declares neither, and reading its first argument as a declaration reported three duplicate
#: declarations in a diagram that draws each element once and then relates it several times.
#:
#: Structural rather than a list of relation macro names. `Rel_` is one dialect's spelling, and an
#: allowlist of it is the same bet the end-anchored alias readings lost; every macro that declares
#: something labels it, and every macro that relates two things names the second one bare.
_MACRO_CALL = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\(\s*(?P<alias>[A-Za-z0-9_-]+)\s*(?:\)|,\s*(?:\"|$))"
)


@dataclass(frozen=True)
class AliasDeclaration:
    """The alias a line declares, and whether that line also opens a containment block."""

    alias: str
    opens_block: bool


def alias_declared_on(line: str) -> AliasDeclaration | None:
    """The declaration this line makes, or None. Comments declare nothing."""
    stripped = line.strip()
    if not stripped or stripped.startswith("'"):
        return None
    without_labels = _QUOTED.sub('""', stripped)
    match = _DECLARATION.search(without_labels)
    if match is None:
        return None
    return AliasDeclaration(alias=match.group("alias"), opens_block=without_labels.endswith("{"))


def macro_alias_declared_on(line: str) -> str | None:
    """The alias a macro-call line declares as its first argument, or None.

    None for a line that *relates* two aliases rather than declaring one — see `_MACRO_CALL`. The
    over-reading was harmless to the only consumer it had, which collects a set and asks "is this
    declared anywhere", so a spurious member failed open. It is wrong for any counting question,
    and E318's duplicate-alias check had to sidestep it by counting the `as` form alone.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("'"):
        return None
    match = _MACRO_CALL.match(stripped)
    return match.group("alias") if match is not None else None


def declared_aliases(body: str) -> list[AliasDeclaration]:
    """Every declaration in *body*, in the order declared."""
    found = [alias_declared_on(line) for line in body.splitlines()]
    return [declaration for declaration in found if declaration is not None]
