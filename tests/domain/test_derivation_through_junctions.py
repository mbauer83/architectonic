"""A junction is one relationship, split or joined — so derivation passes straight through it.

Composition refused junctions outright, and the restriction set refused them a second time: `RJ1`
requires an intermediate's domain to match an endpoint's, and a junction's derivation domain is
`relationships` precisely because it stands for a relationship rather than an element — so it never
matched, and every junction-mediated derivation was disallowed.

The cost was invisible in exactly the place it mattered. `eligible_realizer_types` excludes junctions
as structural helpers (rightly: a junction realizes nothing), so a requirement realized through an
AND-junction found only the junction, found it ineligible, and reported the requirement unrealized
against a model that was correct. Impact analysis stopped at junctions for the same reason.

Certainty is the part that distinguishes this from a grouping: a junction *is* the relationship, so what
comes out is the same relationship between the real endpoints — certain. A grouping's members only
*potentially* carry the whole's relationship, which is why `PDR12` is declared potential.
"""

from __future__ import annotations

import pytest

from src.application.viewpoints.trace_index import build_trace_graph_index
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=5.0)
_REF = frozenset({"archimate-realization", "archimate-aggregation", "archimate-serving"})


def _e(entity_id: str, artifact_type: str, domain: str):
    return entity(artifact_id=entity_id, artifact_type=artifact_type, domain=domain, status="active", name=entity_id)


def _c(source: str, target: str, conn_type: str):
    return connection(artifact_id=f"{source}->{target}:{conn_type}", source=source, target=target, conn_type=conn_type)


def _index(entities, connections):
    return build_trace_graph_index(
        Store(entities={e.artifact_id: e for e in entities}, connections=connections),
        get_module_registry(),
        referenced_connection_types=_REF,
        requirement_type="requirement",
        bounds=_BOUNDS,
    )


def _junction_fixture(junction_type: str, *, second_leg: str = "archimate-realization"):
    entities = [
        _e("JUN@1", junction_type, "common"),
        _e("APP@1", "application-component", "application"),
        _e("APP@2", "application-component", "application"),
        _e("REQ@1", "requirement", "motivation"),
    ]
    connections = [
        _c("APP@1", "JUN@1", "archimate-realization"),
        _c("APP@2", "JUN@1", "archimate-realization"),
        _c("JUN@1", "REQ@1", second_leg),
    ]
    return _index(entities, connections)


@pytest.mark.parametrize("junction_type", ["and-junction", "or-junction"])
def test_the_participants_realize_what_the_junction_realizes(junction_type: str) -> None:
    """Both flavours derive: AND and OR differ in what the combination *means*, not in certainty."""
    realizers = _junction_fixture(junction_type).realizers_of("REQ@1")

    assert {"APP@1", "APP@2"} <= realizers


@pytest.mark.parametrize("junction_type", ["and-junction", "or-junction"])
def test_a_requirement_behind_a_junction_has_an_eligible_realizer(junction_type: str) -> None:
    """The whole point: the junction itself is ineligible, so without this the row was a false gap."""
    from src.application.viewpoints.trace_realizers import eligible_realizer_types

    eligible = eligible_realizer_types(get_module_registry())
    index = _junction_fixture(junction_type)

    assert "and-junction" not in eligible and "or-junction" not in eligible
    assert any(index.type_of.get(realizer) in eligible for realizer in index.realizers_of("REQ@1"))


def test_legs_of_different_types_do_not_compose() -> None:
    """A junction joins relationships of ONE type; a mismatch is a modelling error, not a chain.

    Deriving a weakest-of here would launder that error into a fact the model never stated.
    """
    realizers = _junction_fixture("and-junction", second_leg="archimate-serving").realizers_of("REQ@1")

    assert "APP@1" not in realizers


def test_a_grouping_reaches_its_member_only_potentially() -> None:
    """The contrast that makes the certainty distinction real rather than decorative.

    Both constructs let the leaf find an eligible realizer, so both pass — but a grouping's member is
    reached by inference (`PDR12`, potential) and a junction's participant by pass-through (certain), and
    the result has to be able to say which. Asserting the member's *absence* would be wrong now: it is
    present, and what differs is the standing of the evidence.
    """
    from src.application.viewpoints.trace_realizers import eligible_realizer_types

    eligible = eligible_realizer_types(get_module_registry())
    grouping = _index(
        [
            _e("GRP@1", "grouping", "common"),
            _e("APP@1", "application-component", "application"),
            _e("REQ@1", "requirement", "motivation"),
        ],
        [_c("GRP@1", "REQ@1", "archimate-realization"), _c("GRP@1", "APP@1", "archimate-aggregation")],
    )
    junction = _junction_fixture("and-junction")

    assert "APP@1" in grouping.realizers_of("REQ@1")
    assert grouping.realized_only_potentially("REQ@1", eligible) is True
    assert junction.realized_only_potentially("REQ@1", eligible) is False
