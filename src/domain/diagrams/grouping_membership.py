"""Which grouping each thing a diagram draws sits in: a listed grouping claims first, then the most specific rule.

Stated once, over whatever a caller identifies a drawing by — the renderer places aliases, the
verifier instance ids — so the picture and the check cannot disagree about who is inside a box.

* A **listed** grouping holds the members it names. A drawing is in one listed grouping only: the
  first to name it, in document order.
* A **ruled** grouping holds what its rule admits *of what its parent holds*: a ruled grouping at the
  top takes from everything no listed grouping claimed, one nested in another grouping takes from
  that grouping's members. So a member settles as deep as rules admit it, which is what "the most
  specific rule" means; between sibling rules that both admit it, a type outranks a domain and the
  earlier entry outranks the later.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.authored_groupings import GroupingRule, rule_of
from src.domain.diagrams.recorded_references import GROUPING_MEMBERS_KEY, GROUPING_SUBGROUPS_KEY


@dataclass(frozen=True)
class PlacedGrouping[Drawing: Hashable]:
    """One grouping with the drawings that settled in it, and its subgroups likewise."""

    declaration: Mapping[str, object]
    members: tuple[Drawing, ...]
    groups: tuple[PlacedGrouping[Drawing], ...] = ()

    def is_empty(self) -> bool:
        """True when nothing would be drawn in it — no member at any depth."""
        return not self.members and all(group.is_empty() for group in self.groups)

    def every_member(self) -> Iterator[Drawing]:
        yield from self.members
        for group in self.groups:
            yield from group.every_member()

    def every_grouping(self) -> Iterator[PlacedGrouping[Drawing]]:
        yield self
        for group in self.groups:
            yield from group.every_grouping()


@dataclass(frozen=True)
class Placement[Drawing: Hashable]:
    """Every grouping with its members, and the drawings no grouping holds."""

    groupings: tuple[PlacedGrouping[Drawing], ...]
    unclaimed: tuple[Drawing, ...]

    def every_grouping(self) -> Iterator[PlacedGrouping[Drawing]]:
        for grouping in self.groupings:
            yield from grouping.every_grouping()


@dataclass(frozen=True)
class DrawingTraits[Drawing: Hashable]:
    """What a rule asks of a drawing, answered by the caller that knows what a drawing is."""

    domain_of: Callable[[Drawing], str]
    type_of: Callable[[Drawing], str]

    def admits(self, rule: GroupingRule, drawing: Drawing) -> bool:
        asked = self.domain_of if rule.kind == "domain" else self.type_of
        return asked(drawing) == rule.value


def _entries(groupings: object) -> list[Mapping[str, object]]:
    return [entry for entry in groupings if isinstance(entry, Mapping)] if isinstance(groupings, list) else []


def _settled[Drawing: Hashable](
    groupings: object,
    offered: Sequence[Drawing],
    claims: Mapping[int, list[Drawing]],
    traits: DrawingTraits[Drawing],
) -> tuple[tuple[PlacedGrouping[Drawing], ...], tuple[Drawing, ...]]:
    """The groupings of one level with what settles in each, and what of *offered* none of them took."""
    entries = _entries(groupings)
    ruled = [(entry, rule) for entry in entries if (rule := rule_of(entry)) is not None]
    # A type outranks a domain between siblings; the sort is stable, so document order breaks ties.
    by_specificity = sorted(ruled, key=lambda pair: pair[1].kind != "type")
    taken: dict[int, list[Drawing]] = {id(entry): [] for entry, _rule in ruled}
    left: list[Drawing] = []
    for drawing in offered:
        taker = next((entry for entry, rule in by_specificity if traits.admits(rule, drawing)), None)
        (taken[id(taker)] if taker is not None else left).append(drawing)
    placed: list[PlacedGrouping[Drawing]] = []
    for entry in entries:
        holds = taken[id(entry)] if id(entry) in taken else claims.get(id(entry), [])
        subgroups, own = _settled(entry.get(GROUPING_SUBGROUPS_KEY), holds, claims, traits)
        placed.append(PlacedGrouping(entry, own, subgroups))
    return tuple(placed), tuple(left)


def place_in_groupings[Drawing: Hashable](
    groupings: object,
    *,
    drawings: Sequence[Drawing],
    named: Callable[[str], Drawing | None],
    traits: DrawingTraits[Drawing],
) -> Placement[Drawing]:
    """Settle *drawings* into *groupings*.

    *named* resolves a member as an entry names it — an entity id, or an occurrence id — to the
    drawing it means, or None where the diagram draws no such thing. *drawings* are what the rules
    choose from, in the order they are to be drawn; a listed grouping may also claim a drawing that
    is not among them, which is how a member is taken out of an element it would be nested in.
    """
    claims: dict[int, list[Drawing]] = {}
    claimed: set[Drawing] = set()

    def claim(level: object) -> None:
        """Give each listed grouping its members, the first to name a drawing winning it."""
        for entry in _entries(level):
            members = entry.get(GROUPING_MEMBERS_KEY)
            own = claims.setdefault(id(entry), [])
            for name in members if isinstance(members, list) else []:
                drawing = named(str(name).strip())
                if drawing is not None and drawing not in claimed:
                    claimed.add(drawing)
                    own.append(drawing)
            claim(entry.get(GROUPING_SUBGROUPS_KEY))

    claim(groupings)
    free = [drawing for drawing in drawings if drawing not in claimed]
    placed, unclaimed = _settled(groupings, free, claims, traits)
    return Placement(placed, unclaimed)
