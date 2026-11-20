"""Who is in each authored grouping of a body: its members resolved to the records and aliases drawn.

Split from the emitter, which only writes what this decides. Membership itself — a listed grouping
claims first, then the most specific rule — is `src.domain.diagrams.grouping_membership`'s; this
module is the join from what an entry names (an entity id, an occurrence id) to the drawing meant.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

from src.application.artifacts.parsing import normalize_puml_alias
from src.domain.artifact_id import stable_id
from src.domain.diagrams.grouping_membership import DrawingTraits, PlacedGrouping, place_in_groupings
from src.domain.diagrams.recorded_references import GROUPING_RULE_KEY
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering.archimate_occurrences import occurrence_id_of


@dataclass(frozen=True)
class ResolvedGroup:
    """One authored group with its members and subgroups resolved to records and aliases."""

    declaration: dict[str, object]
    members: list[tuple[EntityRecord, str]]
    subgroups: list[ResolvedGroup] = field(default_factory=list)

    @property
    def label(self) -> str:
        return str(self.declaration.get("label", ""))

    @property
    def is_ruled(self) -> bool:
        return GROUPING_RULE_KEY in self.declaration

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


def release_authored_members(
    authored_groupings: list[dict[str, object]],
    render_entities: list[EntityRecord],
    children_map: dict[str, list[EntityRecord]],
    nested_aliases: set[str],
) -> set[str]:
    """Take every authored group's members out of modelled nesting; return the aliases still nested.

    Declared membership in an authored group outranks modelled containment: the relation stays in
    the model, but the picture keeps the user's box. *children_map* is updated in place, as the
    renderer's nesting walk reads it afterwards.
    """
    claimed = claimed_aliases(resolve_authored_members(authored_groupings, render_entities))
    for parent_alias in list(children_map):
        children_map[parent_alias] = [
            child for child in children_map[parent_alias] if normalize_puml_alias(child.display_alias) not in claimed
        ]
    return nested_aliases - claimed


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
        occurrence_id = occurrence_id_of(entity)
        if occurrence_id:
            index[occurrence_id] = entity
            index.setdefault(stable_id(entity.artifact_id), entity)
        else:
            index[stable_id(entity.artifact_id)] = entity
    return index


def resolve_authored_members(
    authored_groupings: list[dict[str, object]],
    render_entities: list[EntityRecord],
    *,
    free: Sequence[EntityRecord] = (),
    domain_of: Callable[[EntityRecord], str] | None = None,
) -> list[ResolvedGroup]:
    """Resolve each authored group's members and subgroups to (record, alias), in declared order.

    A drawing may appear in one listed group only (first declaration wins), which is why membership
    is settled by alias rather than by entity: two drawings of one entity are two things to place.
    Membership in a listed group WINS over modelled containment nesting: the caller uses these
    aliases to release members from the visual-nesting tree before rendering.

    *free* are the drawings a ruled group may choose from. Left empty, only listed membership is
    resolved — which is all the release from nesting asks about.
    """
    index = _member_index(render_entities)
    by_alias = {normalize_puml_alias(entity.display_alias): entity for entity in render_entities}
    by_alias.pop("", None)

    def named(name: str) -> str | None:
        record = index.get(name) or index.get(stable_id(name))
        return (normalize_puml_alias(record.display_alias) or None) if record is not None else None

    placement = place_in_groupings(
        authored_groupings,
        drawings=[alias for entity in free if (alias := normalize_puml_alias(entity.display_alias))],
        named=named,
        traits=DrawingTraits[str](
            domain_of=lambda alias: domain_of(by_alias[alias]) if domain_of is not None else "",
            type_of=lambda alias: by_alias[alias].artifact_type,
        ),
    )

    def resolved(placed: PlacedGrouping[str]) -> ResolvedGroup:
        return ResolvedGroup(
            declaration=dict(placed.declaration),
            members=[(by_alias[alias], alias) for alias in placed.members],
            subgroups=[resolved(group) for group in placed.groups],
        )

    return [resolved(placed) for placed in placement.groupings]
