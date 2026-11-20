"""Emit authored groupings — user-declared boxes the model does not hold.

Authored groupings are CONTENT, not layout: their labels carry information
(a "Write Requests" box says something no element type does), so they render
exactly as declared — before any computed grouping, members in declared order.
Modelled containment wins for a member that is already visually nested.

Three things a group's declaration does not have to say:

* **How it looks.** Members that all sit in one domain give the group that domain's look; members
  drawn from several give the ArchiMate grouping look, which is what a grouping means when it is not
  a layer. The domain and its stereotype are supplied by the caller that owns that vocabulary — this
  module names no domain. An explicit ``stereotype`` still wins, for the group whose look is a
  deliberate exception.
* **Which drawing of an entity it means.** A member may name an occurrence id, so an entity drawn
  twice sits in a different group each time; ``claimed`` is keyed by alias, so one membership per
  *drawing* falls out rather than one per entity.
* **That it is flat.** A group may hold subgroups under ``groups``, nested to any depth, and a
  subgroup's members count towards its ancestors' domain — a box is one thing however deep it goes.
* **Who is in it, one by one.** A group may state a ``rule`` instead of a list — a domain, or an
  element type within its parent — and then holds what the rule admits. Who settles where is
  `src.domain.diagrams.grouping_membership`'s to say; a ruled group's members are laid out by the
  same component canvas a computed domain box uses.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.diagrams.layout.box_aliases import authored_grouping_alias
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering._authored_grouping_members import (
    ResolvedGroup,
    claimed_aliases,
    resolve_authored_members,
)
from src.infrastructure.rendering._diagram_layout import wrapped_grid_lines

#: The look of a group whose members come from more than one domain: the ArchiMate grouping
#: notation (dashed border, no fill), which is what the notation means when a box is not a layer.
MIXED_DOMAIN_STEREOTYPE = "Grouping"


def group_stereotype(
    group: ResolvedGroup,
    *,
    domain_of: Callable[[EntityRecord], str],
    stereotype_of: Callable[[str], str],
) -> str:
    """The look this group should have, derived from what is in it.

    Derived rather than declared because the answer is already in the membership: a box holding one
    domain's elements *is* that domain, and one holding several is a grouping in the ArchiMate sense.
    An explicit ``stereotype`` is honoured ahead of the derivation, so a deliberate exception stays
    expressible — nothing in the repository needs one, which is the point.
    """
    declared = str(group.declaration.get("stereotype") or "").strip()
    if declared:
        return declared
    domains = {domain_of(record) for record in group.all_records()}
    if len(domains) == 1:
        return stereotype_of(next(iter(domains)))
    return MIXED_DOMAIN_STEREOTYPE


def render_authored_groupings(
    authored_groupings: list[dict[str, object]],
    *,
    render_entities: list[EntityRecord],
    nested_aliases: set[str],
    domain_entities: dict[str, list[EntityRecord]],
    render_entity: Callable[..., list[str]],
    domain_of: Callable[[EntityRecord], str],
    stereotype_of: Callable[[str], str],
    direction_hints: dict[tuple[str, str], str] | None = None,
    connected_pairs: frozenset[frozenset[str]] = frozenset(),
    ruled_canvas: RuledCanvas | None = None,
) -> list[str]:
    """Lines for every authored grouping; claimed members leave the domain pools.

    A ruled grouping chooses from what *domain_entities* still holds — the top-level elements no
    element nests — and lays its members out through *ruled_canvas*.

    ``direction_hints`` (when given) receives left/right hints for connections whose
    BOTH endpoints sit in the same group, following the declared member order — so
    intra-group arrows run along the group instead of stacking members vertically.
    Groups chain via their own aliases: a hidden edge from a member of one box to a
    member of another crashes GraphViz."""
    del nested_aliases
    resolved_groups = resolve_authored_members(
        authored_groupings,
        render_entities,
        free=[entity for entities in domain_entities.values() for entity in entities],
        domain_of=domain_of,
    )
    emitter = _GroupEmitter(
        render_entity=render_entity,
        domain_of=domain_of,
        stereotype_of=stereotype_of,
        direction_hints=direction_hints,
        connected_pairs=connected_pairs,
        ruled_canvas=ruled_canvas,
    )
    emitter.order_members = _member_count(resolved_groups) <= _HIDDEN_CHAIN_MEMBER_BUDGET
    lines = emitter.emit(resolved_groups, indent="")
    taken_aliases = claimed_aliases(resolved_groups)
    for domain in list(domain_entities):
        domain_entities[domain] = [
            entity
            for entity in domain_entities[domain]
            if normalize_puml_alias(entity.display_alias) not in taken_aliases
        ]
    return lines


#: Above this many boxed members, the hidden ordering chains are dropped.
#:
#: They are a *cosmetic* hint — they line members up inside their box — and at scale they stop being
#: free: a 35-node view across 7 boxes made GraphViz throw `IllegalStateException` from
#: `DotStringFactory.solve`, and PlantUML answered by writing a page of stack trace where the picture
#: should be. Bisected against the repo's own `plantuml.jar`: removing only the `-[hidden]` lines
#: renders the same view in ~2 s. The clusters are fine and `linetype ortho` is not the trigger.
#:
#: A threshold rather than removing them outright because below it they are what makes a small boxed
#: view read in a sensible order, and small boxed views are the common case.
_HIDDEN_CHAIN_MEMBER_BUDGET = 24


def _member_count(groups: list[ResolvedGroup]) -> int:
    return sum(len(group.members) + _member_count(group.subgroups) for group in groups)


#: Lays out a ruled grouping's own members inside its box: the members, the box's stereotype, the
#: indent of what goes inside, and a namespace keeping this canvas's aliases apart from another's.
RuledCanvas = Callable[[list[EntityRecord], str, str, str], list[str]]


@dataclass
class _GroupEmitter:
    """Emits a group tree, allocating one alias per box and ranking siblings at each level."""

    render_entity: Callable[..., list[str]]
    domain_of: Callable[[EntityRecord], str]
    stereotype_of: Callable[[str], str]
    direction_hints: dict[tuple[str, str], str] | None
    connected_pairs: frozenset[frozenset[str]]
    ruled_canvas: RuledCanvas | None = None
    #: Set once from the whole tree, so a nested `emit` cannot re-decide it per level.
    order_members: bool = True
    _counter: int = 0
    _rank_by_alias: dict[str, int] = field(default_factory=dict)

    def emit(self, groups: list[ResolvedGroup], *, indent: str) -> list[str]:
        lines: list[str] = []
        previous_alias: str | None = None
        previous_members: list[str] = []
        for group in groups:
            if group.is_empty():
                continue
            self._counter += 1
            rank = self._counter
            group_alias = authored_grouping_alias(rank)
            stereotype = group_stereotype(group, domain_of=self.domain_of, stereotype_of=self.stereotype_of)
            lines.append(f'{indent}rectangle "{group.label}" <<{stereotype}>> as {group_alias} {{')
            member_aliases = group.own_aliases()
            canvas = self.ruled_canvas if group.is_ruled else None
            if canvas is not None:
                # The canvas orders and chains what it lays out, as it does inside a domain box.
                own = [record for record, _alias in group.members]
                lines.extend(canvas(own, stereotype, indent + "  ", f"{group_alias}_"))
            else:
                for record, _alias in group.members:
                    lines.extend(self.render_entity(record, indent + "  ", "right"))
            lines.extend(self.emit(group.subgroups, indent=indent + "  "))
            lines.append(f"{indent}}}")

            if canvas is None:
                lines.extend(self._chain(member_aliases, indent=indent))
                self._hint_within(member_aliases)
            for alias in member_aliases:
                self._rank_by_alias[alias] = rank

            # A hidden edge between two boxes crashes GraphViz shape-dependently; when
            # arrows already join the groups, their direction hints do the ranking.
            connected = any(
                frozenset((prev, curr)) in self.connected_pairs
                for prev in previous_members
                for curr in member_aliases
            )
            if previous_alias and not connected and self.order_members:
                lines.append(f"{indent}{previous_alias} -[hidden]down- {group_alias}")
            previous_alias, previous_members = group_alias, member_aliases
            lines.append("")
        self._hint_across()
        return lines

    def _chain(self, member_aliases: list[str], *, indent: str) -> list[str]:
        if not self.order_members:
            return []
        if len(member_aliases) > 4:
            return wrapped_grid_lines(member_aliases, main_axis="right", cross_axis="down", indent=indent)
        return [
            f"{indent}{member_aliases[idx]} -[hidden]right- {member_aliases[idx + 1]}"
            for idx in range(len(member_aliases) - 1)
        ]

    def _hint_within(self, member_aliases: list[str]) -> None:
        if self.direction_hints is None:
            return
        order = {alias: idx for idx, alias in enumerate(member_aliases)}
        for src in member_aliases:
            for tgt in member_aliases:
                if src != tgt:
                    self.direction_hints.setdefault((src, tgt), "right" if order[tgt] > order[src] else "left")

    def _hint_across(self) -> None:
        # An arrow between two different authored groups follows the DECLARED group
        # order — the authored top-down organization is intentional and outranks the
        # arrow's natural rank direction.
        if self.direction_hints is None:
            return
        for src, src_rank in self._rank_by_alias.items():
            for tgt, tgt_rank in self._rank_by_alias.items():
                if src_rank != tgt_rank:
                    self.direction_hints.setdefault((src, tgt), "down" if tgt_rank > src_rank else "up")
