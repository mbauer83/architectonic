"""Parse labeled grouping rectangles out of a PUML body.

A grouping rectangle carries a ``<<…Grouping>>`` stereotype
(`rectangle "Write Requests" <<CommonGrouping>> as GRP_WRITE {`, the alias being
optional): it exists only in the picture, carries information the model does not
(its label), and its members are the element declarations inside its braces.
Entity rectangles carry an element-type stereotype, never a grouping one — the
stereotype is the discriminator, not the alias (some hand-authored groupings are
aliased, some are not).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.application.puml_alias_declarations import alias_declared_on

#: A labelled grouping opening a block. What sits between the stereotype and the brace is not this
#: pattern's business — it tolerated `as \w+` and so spelled the alias syntax a fourth time, which
#: also meant a *coloured* grouping open (`… <<CommonGrouping>> as G1 #EEE {`) matched nothing and its
#: label was lost. The alias, where there is one, belongs to `puml_alias_declarations`.
_GROUP_OPEN = re.compile(
    r'^\s*rectangle\s+"(?P<label>[^"]+)"\s+<<(?P<stereotype>[^>]*Grouping)>>.*\{\s*$'
)
#: A member declaration is read by `puml_alias_declarations`, shared with every other caller. The
#: regex this replaces ended at the alias and spelled it `\w+`, so it lost both an alias carrying a
#: hyphen and any element whose declaration carries a trailing colour — a grouping's members are
#: exactly the elements it must not drop when a body is preserved.


@dataclass(frozen=True)
class LabeledGrouping:
    """One labeled, alias-less grouping rectangle and its member aliases in drawn order."""

    label: str
    stereotype: str
    member_aliases: tuple[str, ...]


def parse_labeled_groupings(puml_body: str) -> list[LabeledGrouping]:
    """Every labeled grouping rectangle in *puml_body* with its DIRECT member aliases.

    Members are the aliased element declarations at any depth inside the grouping's
    braces (a nested entity box's own children belong to the entity, but they are
    still members of the grouping for preservation purposes — they travel with it).
    Nested labeled groupings are returned as their own entries; their members are
    not double-counted into the outer grouping.
    """
    groupings: list[LabeledGrouping] = []
    # Stack of (is_labeled_grouping, collector-or-None, label, stereotype)
    stack: list[tuple[bool, list[str] | None, str, str]] = []

    def _current_collector() -> list[str] | None:
        for is_grouping, collector, _label, _stereo in reversed(stack):
            if is_grouping:
                return collector
        return None

    for raw_line in puml_body.splitlines():
        line = raw_line.rstrip()
        opened = _GROUP_OPEN.match(line)
        if opened:
            stack.append((True, [], opened.group("label"), opened.group("stereotype").strip()))
            continue
        declaration = alias_declared_on(line)
        if declaration is not None:
            collector = _current_collector()
            if collector is not None:
                collector.append(declaration.alias)
        if line.endswith("{") and not opened:
            stack.append((False, None, "", ""))
            continue
        if line.strip() == "}":
            if stack:
                is_grouping, collector, label, stereotype = stack.pop()
                if is_grouping and collector is not None:
                    groupings.append(
                        LabeledGrouping(
                            label=label, stereotype=stereotype, member_aliases=tuple(dict.fromkeys(collector))
                        )
                    )
    return groupings
