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

_GROUP_OPEN = re.compile(
    r'^\s*rectangle\s+"(?P<label>[^"]+)"\s+<<(?P<stereotype>[^>]*Grouping)>>\s*(?:as\s+\w+\s*)?\{\s*$'
)
_ALIAS_DECL = re.compile(r'\bas\s+(?P<alias>[A-Za-z0-9_]+)\s*(\{\s*)?$')


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
        alias_match = _ALIAS_DECL.search(line)
        if alias_match and not line.lstrip().startswith("'"):
            collector = _current_collector()
            if collector is not None:
                collector.append(alias_match.group("alias"))
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
