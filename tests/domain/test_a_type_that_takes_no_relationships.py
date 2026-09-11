"""A type declaring it takes no relationships is absent from the permitted-relationship table.

The rules are written in terms of `@all` and element classes — association with anything,
composition and specialization with its own kind, the eleven junction relationships — so every
entity type is swept into them by existing. A record *about* an artifact rather than a participant
in the model is therefore permitted, at type level, to carry relationships its own declaration
forbids: `proposed-change` says "nothing may attach to it in either direction" and measured 79
outgoing and 81 incoming.

That is not merely a stale table. `permits()` is what the write path asks before accepting a
connection, so the two disagreeing means the product would accept one.

The flag is deliberately not `internal`. A global artifact reference is internal too, and it *does*
carry a connection surface — it is a proxy for an enterprise artifact that participates, narrowed
per instance at validation time. The distinction is asserted here so a later change cannot collapse
the two and silently detach every reference.
"""

from __future__ import annotations

import pytest

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.ontologies.archimate_4 import module
from src.ontologies.archimate_4._yaml_data import build_permitted_relationships

DETACHED = EntityTypeName("proposed-change")
REFERENCE = EntityTypeName("global-artifact-reference")


def _surface(entity_type: EntityTypeName) -> tuple[int, int]:
    """(outgoing, incoming) permitted relationships for *entity_type*."""
    by_source = module.permitted_relationships.by_source()
    outgoing = len(by_source.get(entity_type, []))
    incoming = sum(1 for pairs in by_source.values() for target, _ in pairs if target == entity_type)
    return outgoing, incoming


class TestTheShippedOntology:
    def test_a_proposed_change_is_not_a_participant_in_either_direction(self) -> None:
        assert _surface(DETACHED) == (0, 0)

    def test_no_connection_may_be_accepted_against_one(self) -> None:
        """The table is what `permits()` answers from, and the write path asks it."""
        for other in module.entity_types:
            for connection in module.connection_types:
                assert not module.permitted_relationships.permits(other, DETACHED, connection)
                assert not module.permitted_relationships.permits(DETACHED, other, connection)

    def test_a_global_artifact_reference_still_participates(self) -> None:
        """Internal, and a participant: the flag distinguishes the two, and must go on saying so."""
        outgoing, incoming = _surface(REFERENCE)
        assert outgoing > 0 and incoming > 0
        assert module.entity_types[REFERENCE].internal
        assert not module.entity_types[REFERENCE].takes_no_relationships


def _entity_types(**flags: bool) -> dict[EntityTypeName, EntityTypeInfo]:
    def info(name: str, *, detached: bool) -> EntityTypeInfo:
        return EntityTypeInfo(
            artifact_type=name,
            prefix=name[:3].upper(),
            hierarchy=("common", name),
            classes=("thing",),
            create_when="",
            never_create_when="",
            takes_no_relationships=detached,
        )

    return {EntityTypeName(n): info(n, detached=d) for n, d in flags.items()}


class TestTheRuleExpansion:
    """Stated over what the rule language permits, not over the shipped file's current contents."""

    def test_a_general_rule_does_not_reach_a_detached_type(self) -> None:
        built = build_permitted_relationships(
            {"permitted_relationships": [["@all", "@all", ["association"]]]},
            _entity_types(participant=False, detached=True),
        )

        assert built.permits(
            EntityTypeName("participant"), EntityTypeName("participant"), ConnectionTypeName("archimate-association")
        )
        assert not built.permits(
            EntityTypeName("participant"), EntityTypeName("detached"), ConnectionTypeName("archimate-association")
        )

    def test_a_class_reference_does_not_reach_one_either(self) -> None:
        built = build_permitted_relationships(
            {"permitted_relationships": [["@thing", "@thing", ["association"]]]},
            _entity_types(participant=False, detached=True),
        )

        assert not built.permits(
            EntityTypeName("detached"), EntityTypeName("participant"), ConnectionTypeName("archimate-association")
        )

    def test_naming_one_outright_is_refused_rather_than_dropped(self) -> None:
        """A rule naming it and a declaration forbidding it contradict; the file must not hold both."""
        with pytest.raises(ValueError, match="takes_no_relationships"):
            build_permitted_relationships(
                {"permitted_relationships": [["participant", "detached", ["association"]]]},
                _entity_types(participant=False, detached=True),
            )
