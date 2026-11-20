"""A stored diagram's layout, joined to the aliases a picture of the diagram draws things under.

The one place a frontmatter becomes a `LaidOutDiagram`: the layout it states, and for everything the
layout may name the alias the product draws it under. Every image path asks here, so the stored
picture, a lensed view and a download cannot disagree about which diagrams are drawn from a layout
or about what a key of one means.

A diagram is drawn from its layout only when it states one that can be read and may carry one. A
``manual-layout`` diagram keeps its hand-written body; a block that cannot be read is the verifier's
to report (E370) and the picture falls back to the arrangement the renderer chose, which is always
available. So is a layout that states nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.application.modeling.diagram_identities import (
    alias_by_instance,
    drawn_instances,
    drawn_relation_ends,
    occurrences_stated,
    strings_of,
)
from src.domain.artifact_id import MalformedArtifactIdError, canonical_entity_key, parse_entity_id
from src.domain.diagrams.authored_groupings import GROUPING_ID_KEY, check_groupings, states_a_ruled_grouping
from src.domain.diagrams.grouping_membership import DrawingTraits, PlacedGrouping, place_in_groupings
from src.domain.diagrams.layout.laid_out_diagram import DrawnKind, LaidOutDiagram, StatedGrouping
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout, MalformedLayout, read_layout
from src.domain.ontology_representation.ontology_types import EntityTypeInfo


class DeclaresElementKinds(Protocol):
    """What this asks of the ontology: which type an id's prefix names, and which domain that type is of."""

    def entity_type_prefixes(self) -> Mapping[str, str]: ...

    def all_entity_types(self) -> Mapping[str, EntityTypeInfo]: ...


def stated_layout(frontmatter: Mapping[str, object]) -> Layout | None:
    """The layout *frontmatter* states and its diagram may be drawn from, or None for PlantUML's own."""
    if LAYOUT_KEY not in frontmatter or frontmatter.get("manual-layout") is True:
        return None
    try:
        layout = read_layout(frontmatter[LAYOUT_KEY])
    except MalformedLayout:
        return None
    return None if layout.states_nothing() else layout


def _kinds(
    frontmatter: Mapping[str, object], aliases: Mapping[str, str], ontology: DeclaresElementKinds
) -> dict[str, DrawnKind]:
    """What each drawn instance is, by alias: an occurrence is what its backing entity is."""
    backing = dict(occurrences_stated(frontmatter.get("diagram-entities"), frontmatter.get("bindings")))
    type_of_prefix, types = ontology.entity_type_prefixes(), ontology.all_entity_types()
    kinds: dict[str, DrawnKind] = {}
    for instance, alias in aliases.items():
        try:
            prefix = parse_entity_id(backing.get(instance, instance)).prefix
        except MalformedArtifactIdError:
            continue
        info = types.get(type_of_prefix.get(prefix, ""))
        if info is not None:
            kinds[alias] = DrawnKind(info.hierarchy[0] if info.hierarchy else "common", info.artifact_type)
    return kinds


def _stated(placed: PlacedGrouping[str], aliases: Mapping[str, str]) -> StatedGrouping:
    return StatedGrouping(
        grouping_id=str(placed.declaration.get(GROUPING_ID_KEY) or ""),
        members=tuple(aliases[member] for member in placed.members if member in aliases),
        groups=tuple(_stated(group, aliases) for group in placed.groups),
    )


def _groupings(
    frontmatter: Mapping[str, object], aliases: Mapping[str, str], kinds: Mapping[str, DrawnKind]
) -> tuple[StatedGrouping, ...]:
    """The groupings the diagram states with who settled in each; none where the statement is not sound."""
    stated = frontmatter.get("authored-groupings")
    if not stated or check_groupings(stated):
        return ()
    instances = drawn_instances(
        strings_of(frontmatter.get("entity-ids-used")), frontmatter.get("diagram-entities"), frontmatter.get("bindings")
    )

    def kind_of(instance: str) -> DrawnKind | None:
        return kinds.get(aliases.get(instance, ""))

    traits = DrawingTraits[str](
        domain_of=lambda instance: kind.domain if (kind := kind_of(instance)) else "",
        type_of=lambda instance: kind.element_type if (kind := kind_of(instance)) else "",
    )
    placement = place_in_groupings(
        stated,
        drawings=sorted(instances),
        named=lambda name: key if (key := canonical_entity_key(name)) in instances else None,
        traits=traits,
    )
    return tuple(_stated(placed, aliases) for placed in placement.groupings)


def laid_out_diagram(frontmatter: Mapping[str, object], ontology: DeclaresElementKinds) -> LaidOutDiagram | None:
    """*frontmatter*'s layout with its joins to a picture made, or None where the diagram is drawn without one."""
    layout = stated_layout(frontmatter)
    if layout is None:
        return None
    aliases = alias_by_instance(frontmatter)
    kinds = _kinds(frontmatter, aliases, ontology)
    ends = drawn_relation_ends(
        strings_of(frontmatter.get("connection-ids-used")), frontmatter.get("diagram-entities"),
        frontmatter.get("connections"), frontmatter.get("bindings"),
    )
    return LaidOutDiagram(
        layout=layout,
        instance_by_alias={alias: instance for instance, alias in aliases.items()},
        relations={
            key: (aliases[source], aliases[target])
            for key, (source, target) in ends.items()
            if source in aliases and target in aliases
        },
        groupings=_groupings(frontmatter, aliases, kinds),
        kinds=kinds,
        boxes_are_computed=not states_a_ruled_grouping(frontmatter.get("authored-groupings")),
    )
