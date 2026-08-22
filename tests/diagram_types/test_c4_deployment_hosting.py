"""What may host an artifact, and what the deployment projection reads — kept in step by derivation.

The projection listed five host types and the relationship table permitted the first hop of the
deployment chain from exactly one of them, so four of five were declarable hosts that nothing could
be deployed on: a model whose only hosting relation was `system-software --aggregation--> artifact`
could not state it, and a deployment view over such a model drew no containers at all. Two literals
three lines apart were each out of step with the table, one too narrow and one too wide.

Assignment is ArchiMate's deployment relation — a node is assigned to an artifact to say the artifact
is deployed on it — so permitting it is standard-conformant, and it only loosens the table, so no
model that verified before stops verifying.

Aggregation stays scoped to the one pair that was already permitted, rather than widening with
assignment: the models it exists for can only have used that pair, and widening it would break the
composition-mirrors-aggregation invariant (spec §5.1.2) in four new places, whose one documented
exception is exactly that pair.

**Three assertions, one per pair, deliberately not one combined.** A single gate over "the hosting
types" would have made one pair's requirement drive the other pair's fix, and it would have driven
the wrong one: composition is illegitimate for the artifact pair and legitimate — and used six times
in the shipped self-model — for the host-to-host pair. Which is why there are two sets.
"""

from __future__ import annotations

import pytest

from src.diagram_types.c4._projection_deployment import (
    _ARTIFACT_HOSTING_TYPES,
    _HOST_CLASS,
    _NODE_CONTAINMENT_TYPES,
    _deployment_host_types,
)
from src.domain.modules.module_types import EntityTypeName


def _permitted():
    from src.infrastructure.app_bootstrap import get_module_registry

    return get_module_registry().aggregated_permitted_relationships()


def _host_types() -> list[str]:
    return sorted(_deployment_host_types())


class TestTheHostSetIsTheClassThatDefinesIt:
    def test_it_is_derived_from_the_ontology_not_listed(self) -> None:
        from src.infrastructure.app_bootstrap import get_module_registry

        assert _deployment_host_types() == frozenset(
            str(name) for name in get_module_registry().entity_types_with_class(_HOST_CLASS)
        )

    def test_the_class_has_members(self) -> None:
        """A derived set cannot drift, but it can be derived from a class that stopped existing."""
        assert _host_types()


class TestEveryHostCanBeDeployedOn:
    """The assertion a derived set cannot make about itself, and the one the report asked for —
    pointed the other way: every member of the host class has a permitted relation to `artifact`."""

    @pytest.mark.parametrize("host", _host_types())
    def test_the_host_has_a_permitted_relation_to_an_artifact(self, host: str) -> None:
        permitted = _permitted().permitted_connection_types(
            EntityTypeName(host), EntityTypeName("artifact")
        )

        assert permitted, f"{host} is a declared deployment host with no way to hold an artifact"

    @pytest.mark.parametrize("host", _host_types())
    def test_assignment_is_among_them(self, host: str) -> None:
        """The deployment relation itself, not merely something."""
        permitted = {
            str(c)
            for c in _permitted().permitted_connection_types(
                EntityTypeName(host), EntityTypeName("artifact")
            )
        }

        assert "archimate-assignment" in permitted, f"{host} cannot be assigned to an artifact"


class TestWhatTheProjectionReadsIsWhatTheTablePermits:
    def test_every_artifact_hosting_type_is_permitted_from_some_host_to_an_artifact(self) -> None:
        """Closes the drift in the other direction: the reader held `archimate-composition`, which
        the table permits from no host to an artifact at all, so no valid model could ever have one
        and the reader was looking for something that could not exist.

        Stated over the class rather than per host, because the two members are scoped differently on
        purpose. Assignment is permitted from every host — that is the fix. Aggregation is permitted
        from `technology-node` alone and is deliberately not widened with it: it is read only for the
        models authored while it was the only path the table offered, which can only be that pair,
        and widening it would break the composition-mirrors-aggregation invariant in four new places.
        """
        reachable = {
            str(conn)
            for host in _host_types()
            for conn in _permitted().permitted_connection_types(
                EntityTypeName(host), EntityTypeName("artifact")
            )
        }

        assert _ARTIFACT_HOSTING_TYPES <= reachable, (
            f"the projection reads {sorted(_ARTIFACT_HOSTING_TYPES - reachable)} into an artifact, "
            f"which the table permits from no deployment host"
        )

    @pytest.mark.parametrize("host", _host_types())
    def test_every_node_containment_type_is_permitted_from_the_host_to_itself(self, host: str) -> None:
        permitted = {
            str(c)
            for c in _permitted().permitted_connection_types(EntityTypeName(host), EntityTypeName(host))
        }

        assert _NODE_CONTAINMENT_TYPES <= permitted, (
            f"{host}: the projection reads {sorted(_NODE_CONTAINMENT_TYPES - permitted)} "
            f"between hosts, which the table does not permit"
        )

    def test_the_two_sets_are_not_the_same_set(self) -> None:
        """They answer different questions, and one literal for both is what created the defect.

        Composition belongs to the containment pair and not to the artifact pair. Merging them —
        which the first reading of this defect proposed — would either refuse what the self-model
        already states, or read a relation into artifact hosting that no model can hold.
        """
        assert "archimate-composition" in _NODE_CONTAINMENT_TYPES
        assert "archimate-composition" not in _ARTIFACT_HOSTING_TYPES
        assert "archimate-assignment" in _ARTIFACT_HOSTING_TYPES

    def test_neither_set_reads_serving_as_hosting(self) -> None:
        """A standing non-goal. `serving` is the only direct technology-to-application rule, so it
        looks like the obvious substitute for a missing hosting path, and it means the opposite:
        ArchiMate separates assignment, which allocates, from serving, which consumes. A dependency
        on a broker or a store would be drawn as a host."""
        assert "archimate-serving" not in _ARTIFACT_HOSTING_TYPES | _NODE_CONTAINMENT_TYPES
