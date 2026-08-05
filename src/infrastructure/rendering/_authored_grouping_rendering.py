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
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering._diagram_layout import wrapped_grid_lines

#: The look of a group whose members come from more than one domain: the ArchiMate grouping
#: notation (dashed border, no fill), which is what the notation means when a box is not a layer.
MIXED_DOMAIN_STEREOTYPE = "Grouping"


@dataclass(frozen=True)
class ResolvedGroup:
    """One authored group with its members and subgroups resolved to records and aliases."""

    declaration: dict[str, object]
    members: list[tuple[EntityRecord, str]]
    subgroups: list[ResolvedGroup] = field(default_factory=list)

    @property
    def label(self) -> str:
        return str(self.declaration.get("label", ""))

    def is_empty(self) -> bool:
        """True when nothing would be drawn — no members at any depth."""
        return not self.members and all(subgroup.is_empty() for subgroup in self.subgroups)

    def own_aliases(self) -> list[str]:
        return [alias for _record, alias in self.members]

    def all_aliases(self) -> Iterator[str]:
        """Every alias this group claims, including its subgroups'."""
        yield from self.own_aliases()
        for subgroup in self.subgroups:
            yield from subgroup.all_aliases()

    def all_records(self) -> Iterator[EntityRecord]:
        for record, _alias in self.members:
            yield record
        for subgroup in self.subgroups:
            yield from subgroup.all_records()


def claimed_aliases(resolved: list[ResolvedGroup]) -> set[str]:
    """Every alias any authored group claims, at any depth."""
    return {alias for group in resolved for alias in group.all_aliases()}


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
) -> list[str]:
    """Lines for every authored grouping; claimed members leave the domain pools.

    ``direction_hints`` (when given) receives left/right hints for connections whose
    BOTH endpoints sit in the same group, following the declared member order — so
    intra-group arrows run along the group instead of stacking members vertically.
    Groups chain via their own aliases: a hidden edge from a member of one box to a
    member of another crashes GraphViz."""
    resolved_groups = resolve_authored_members(authored_groupings, render_entities)
    emitter = _GroupEmitter(
        render_entity=render_entity,
        domain_of=domain_of,
        stereotype_of=stereotype_of,
        direction_hints=direction_hints,
        connected_pairs=connected_pairs,
    )
    lines = emitter.emit(resolved_groups, indent="")
    taken_aliases = claimed_aliases(resolved_groups)
    for domain in list(domain_entities):
        domain_entities[domain] = [
            entity
            for entity in domain_entities[domain]
            if normalize_puml_alias(entity.display_alias) not in taken_aliases
        ]
    return lines


@dataclass
class _GroupEmitter:
    """Emits a group tree, allocating one alias per box and ranking siblings at each level."""

    render_entity: Callable[..., list[str]]
    domain_of: Callable[[EntityRecord], str]
    stereotype_of: Callable[[str], str]
    direction_hints: dict[tuple[str, str], str] | None
    connected_pairs: frozenset[frozenset[str]]
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
            group_alias = f"GRPA_{rank}"
            stereotype = group_stereotype(group, domain_of=self.domain_of, stereotype_of=self.stereotype_of)
            lines.append(f'{indent}rectangle "{group.label}" <<{stereotype}>> as {group_alias} {{')
            for record, _alias in group.members:
                lines.extend(self.render_entity(record, indent + "  ", "right"))
            lines.extend(self.emit(group.subgroups, indent=indent + "  "))
            lines.append(f"{indent}}}")

            member_aliases = group.own_aliases()
            lines.extend(self._chain(member_aliases, indent=indent))
            for alias in member_aliases:
                self._rank_by_alias[alias] = rank
            self._hint_within(member_aliases)

            # A hidden edge between two boxes crashes GraphViz shape-dependently; when
            # arrows already join the groups, their direction hints do the ranking.
            connected = any(
                frozenset((prev, curr)) in self.connected_pairs
                for prev in previous_members
                for curr in member_aliases
            )
            if previous_alias and not connected:
                lines.append(f"{indent}{previous_alias} -[hidden]down- {group_alias}")
            previous_alias, previous_members = group_alias, member_aliases
            lines.append("")
        self._hint_across()
        return lines

    def _chain(self, member_aliases: list[str], *, indent: str) -> list[str]:
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


def _member_index(render_entities: list[EntityRecord]) -> dict[str, EntityRecord]:
    """Every way a member may be named → the record it means.

    An entity drawn twice contributes an occurrence record per drawing, each carrying the occurrence
    id in ``host_diagram_id`` and its own ``BASE__n`` alias. Both the entity id and each occurrence id
    resolve, so a group may say "this entity" or "this drawing of it".

    The base record wins the entity id even though the occurrences share its ``artifact_id``: an
    id-keyed index built by last-write would silently hand the *last* drawing to a group that named
    the entity.
    """
    index: dict[str, EntityRecord] = {}
    for entity in render_entities:
        occurrence_id = str(entity.host_diagram_id or "").strip()
        if occurrence_id:
            index[occurrence_id] = entity
            index.setdefault(stable_id(entity.artifact_id), entity)
        else:
            index[stable_id(entity.artifact_id)] = entity
    return index


def resolve_authored_members(
    authored_groupings: list[dict[str, object]],
    render_entities: list[EntityRecord],
) -> list[ResolvedGroup]:
    """Resolve each authored group's members and subgroups to (record, alias), in declared order.

    A drawing may appear in one group only (first declaration wins), which is why ``claimed`` is
    keyed by alias rather than by entity: two drawings of one entity are two things to place.
    Membership in an authored group WINS over modelled containment nesting: the caller uses these
    aliases to release members from the visual-nesting tree before rendering.
    """
    return _resolve(authored_groupings, _member_index(render_entities), claimed=set())


def _resolve(
    authored_groupings: list[dict[str, object]],
    index: dict[str, EntityRecord],
    *,
    claimed: set[str],
) -> list[ResolvedGroup]:
    resolved: list[ResolvedGroup] = []
    for group in authored_groupings:
        if not isinstance(group, dict):
            continue
        member_records: list[tuple[EntityRecord, str]] = []
        raw_members = group.get("entity-ids")
        for raw_id in raw_members if isinstance(raw_members, list) else []:
            named = str(raw_id).strip()
            record = index.get(named) or index.get(stable_id(named))
            alias = normalize_puml_alias(record.display_alias) if record is not None else ""
            if record is None or not alias or alias in claimed:
                continue
            member_records.append((record, alias))
            claimed.add(alias)
        raw_subgroups = group.get("groups")
        subgroups = (
            _resolve([g for g in raw_subgroups if isinstance(g, dict)], index, claimed=claimed)
            if isinstance(raw_subgroups, list)
            else []
        )
        resolved.append(ResolvedGroup(declaration=group, members=member_records, subgroups=subgroups))
    return resolved
