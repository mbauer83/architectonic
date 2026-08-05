"""An aggregate goal is a rollup, not an obligation-bearing row.

The reported defect: a goal realized through the goals it aggregates, rather than directly by an
outcome, was reported `missing-outcome` — which `docs/03-modeling/coverage-semantics.md` defines as an
always-a-gap obligation. The correct structure was penalised, and the only way to keep the view green
was a direct realization edge onto the apex that the model does not otherwise want. A metric shaping
the model instead of measuring it.

An aggregate is not realized; its constituents are. So it bears no missing-* obligation of its own and
carries theirs — which, under the kind's fixed universal quantification over branches, already reads as
"covered exactly when every constituent is". No new quantifier, and no second way to express the chain.
"""

from __future__ import annotations

from src.application.viewpoints.trace_index import build_trace_graph_index
from src.application.viewpoints.trace_obligations import enumerate_row_obligations
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.domain.viewpoints.viewpoint_trace_patterns import (
    NamedBranchEdge,
    RollupEdge,
    StoredEdge,
)
from src.domain.viewpoints.viewpoint_trace_result import (
    MissingOutcomeObligation,
    MissingRequirementObligation,
    TerminalObligation,
)
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REF = frozenset({"archimate-realization", "archimate-aggregation"})
_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=2.0)

_BRANCHES = (
    NamedBranchEdge("goal_to_outcome", StoredEdge("archimate-realization", "incoming", "outcome")),
    NamedBranchEdge("outcome_to_requirement", StoredEdge("archimate-realization", "incoming", "requirement")),
)
#: As the shipped `motivation-coverage` viewpoint declares it: whole -> part, so a row's constituents
#: are the targets of its outgoing aggregation. No endpoint type — it is the row's own type.
_ROLLUP = RollupEdge("archimate-aggregation", "outgoing")

_TYPE = {"GOL": "goal", "OUT": "outcome", "REQ": "requirement"}


def _e(eid: str):
    return entity(artifact_id=eid, artifact_type=_TYPE[eid.split("@")[0]], domain="motivation", status="active")


def _realizes(source: str, target: str):
    return connection(
        artifact_id=f"{source}--{target}", source=source, target=target, conn_type="archimate-realization"
    )


def _aggregates(whole: str, part: str):
    return connection(
        artifact_id=f"{whole}~{part}", source=whole, target=part, conn_type="archimate-aggregation"
    )


def _index(entities, connections):
    store = Store(entities={e.artifact_id: e for e in entities}, connections=connections)
    return build_trace_graph_index(
        store, get_module_registry(), referenced_connection_types=_REF, requirement_type="requirement", bounds=_BOUNDS
    )


def _obligations(entity_id: str, index, *, rollup: RollupEdge | None = _ROLLUP, row_type: str = "goal"):
    return enumerate_row_obligations(entity_id, row_type, _BRANCHES, (), index, rollup)


def _covered_goal(suffix: str):
    """A goal covered the ordinary way: outcome realizes goal, requirement realizes outcome."""
    goal, outcome, requirement = f"GOL@{suffix}", f"OUT@{suffix}", f"REQ@{suffix}"
    return (
        [_e(goal), _e(outcome), _e(requirement)],
        [_realizes(outcome, goal), _realizes(requirement, outcome)],
    )


# ── The reported defect ───────────────────────────────────────────────────────


def test_an_aggregate_goal_whose_constituents_are_covered_is_covered() -> None:
    entities_a, connections_a = _covered_goal("a")
    entities_b, connections_b = _covered_goal("b")
    index = _index(
        [_e("GOL@apex"), *entities_a, *entities_b],
        [*connections_a, *connections_b, _aggregates("GOL@apex", "GOL@a"), _aggregates("GOL@apex", "GOL@b")],
    )

    obligations = _obligations("GOL@apex", index)

    assert obligations.missing == (), "the apex bears no obligation of its own"
    assert {t.requirement_id for t in obligations.terminals} == {"REQ@a", "REQ@b"}


def test_the_same_apex_is_still_a_gap_without_the_rollup_declared() -> None:
    """The control: this is what the view reported, and why the fix had to reach the evaluator."""
    entities_a, connections_a = _covered_goal("a")
    index = _index(
        [_e("GOL@apex"), *entities_a],
        [*connections_a, _aggregates("GOL@apex", "GOL@a")],
    )

    obligations = _obligations("GOL@apex", index, rollup=None)

    assert obligations.missing == (MissingOutcomeObligation("GOL@apex"),)


def test_an_aggregate_is_a_gap_when_one_constituent_is_bare() -> None:
    entities_a, connections_a = _covered_goal("a")
    index = _index(
        [_e("GOL@apex"), *entities_a, _e("GOL@bare")],
        [*connections_a, _aggregates("GOL@apex", "GOL@a"), _aggregates("GOL@apex", "GOL@bare")],
    )

    obligations = _obligations("GOL@apex", index)

    assert obligations.missing == (MissingOutcomeObligation("GOL@bare"),)


def test_a_propagated_obligation_names_the_constituent_it_belongs_to() -> None:
    """Not the apex: a report has to say where the gap is, not who inherited it."""
    index = _index(
        [_e("GOL@apex"), _e("GOL@bare")],
        [_aggregates("GOL@apex", "GOL@bare")],
    )

    obligations = _obligations("GOL@apex", index)

    assert [m.root_id for m in obligations.missing] == ["GOL@bare"]


def test_a_constituents_missing_requirement_reaches_the_aggregate() -> None:
    """The whole chain composes, not just its first hop."""
    index = _index(
        [_e("GOL@apex"), _e("GOL@a"), _e("OUT@a")],
        [_aggregates("GOL@apex", "GOL@a"), _realizes("OUT@a", "GOL@a")],
    )

    obligations = _obligations("GOL@apex", index)

    assert obligations.missing == (MissingRequirementObligation("GOL@a", "OUT@a"),)


# ── What the rollup must not change ───────────────────────────────────────────


def test_a_goal_that_aggregates_nothing_still_owes_an_outcome() -> None:
    """The reason this is not a branch: as a branch it would make aggregation mandatory everywhere."""
    index = _index([_e("GOL@leaf")], [])

    assert _obligations("GOL@leaf", index).missing == (MissingOutcomeObligation("GOL@leaf"),)


def test_an_aggregate_with_its_own_outcome_keeps_that_branch_too() -> None:
    """Union, not either/or: a branch the aggregate does have is still its own to satisfy."""
    entities_a, connections_a = _covered_goal("a")
    index = _index(
        [_e("GOL@apex"), _e("OUT@apex"), *entities_a],
        [*connections_a, _realizes("OUT@apex", "GOL@apex"), _aggregates("GOL@apex", "GOL@a")],
    )

    obligations = _obligations("GOL@apex", index)

    # The apex's own outcome has no requirement, so it is an incomplete branch of the apex …
    assert obligations.missing == (MissingRequirementObligation("GOL@apex", "OUT@apex"),)
    # … while the constituent's requirement still counts toward the same row.
    assert {t.requirement_id for t in obligations.terminals} == {"REQ@a"}


def test_only_peers_of_the_rows_own_type_are_descended() -> None:
    """An aggregated outcome is not a constituent goal — that would be a second, undeclared chain."""
    index = _index(
        [_e("GOL@apex"), _e("OUT@x")],
        [_aggregates("GOL@apex", "OUT@x")],
    )

    assert _obligations("GOL@apex", index).missing == (MissingOutcomeObligation("GOL@apex"),)


def test_a_deprecated_constituent_is_not_descended() -> None:
    """Active-only, as every other branch hop is."""
    index = _index(
        [_e("GOL@apex"), entity(artifact_id="GOL@old", artifact_type="goal", domain="motivation", status="deprecated")],
        [_aggregates("GOL@apex", "GOL@old")],
    )

    assert _obligations("GOL@apex", index).missing == (MissingOutcomeObligation("GOL@apex"),)


# ── Structure that could not otherwise terminate ──────────────────────────────


def test_a_nested_aggregate_composes_through_every_level() -> None:
    entities_a, connections_a = _covered_goal("a")
    index = _index(
        [_e("GOL@apex"), _e("GOL@mid"), *entities_a],
        [*connections_a, _aggregates("GOL@apex", "GOL@mid"), _aggregates("GOL@mid", "GOL@a")],
    )

    obligations = _obligations("GOL@apex", index)

    assert obligations.missing == ()
    assert {t.requirement_id for t in obligations.terminals} == {"REQ@a"}


def test_an_aggregation_cycle_is_reported_rather_than_followed() -> None:
    index = _index(
        [_e("GOL@one"), _e("GOL@two")],
        [_aggregates("GOL@one", "GOL@two"), _aggregates("GOL@two", "GOL@one")],
    )

    obligations = _obligations("GOL@one", index)

    assert obligations.cycle is True


def test_a_self_aggregating_goal_does_not_recurse_forever() -> None:
    index = _index([_e("GOL@self")], [_aggregates("GOL@self", "GOL@self")])

    assert _obligations("GOL@self", index).missing == (MissingOutcomeObligation("GOL@self"),)


def test_a_diamond_is_counted_once_per_path_and_terminates() -> None:
    """Two aggregates sharing a constituent: the shared obligations collapse in the result set."""
    entities_a, connections_a = _covered_goal("a")
    index = _index(
        [_e("GOL@apex"), _e("GOL@left"), _e("GOL@right"), *entities_a],
        [
            *connections_a,
            _aggregates("GOL@apex", "GOL@left"),
            _aggregates("GOL@apex", "GOL@right"),
            _aggregates("GOL@left", "GOL@a"),
            _aggregates("GOL@right", "GOL@a"),
        ],
    )

    obligations = _obligations("GOL@apex", index)

    assert obligations.missing == ()
    assert {t.requirement_id for t in obligations.terminals} == {"REQ@a"}


# ── The same rule at every other level of the chain ───────────────────────────


def test_an_aggregate_requirement_carries_its_constituents_instead_of_itself() -> None:
    """The defect one level down: an aggregate requirement is realized through its parts.

    ArchiMate derivation cannot supply this — the aggregation and the realization both point *at* the
    part, so they compose along no path — which is why the rollup has to hold here too.
    """
    index = _index(
        [_e("REQ@whole"), _e("REQ@part")],
        [_aggregates("REQ@whole", "REQ@part")],
    )

    obligations = _obligations("REQ@whole", index, row_type="requirement")

    assert obligations.terminals == (TerminalObligation("REQ@part", "REQ@part"),)
    assert TerminalObligation("REQ@whole", "REQ@whole") not in obligations.terminals


def test_a_requirement_that_aggregates_nothing_is_still_its_own_obligation() -> None:
    index = _index([_e("REQ@solo")], [])

    obligations = _obligations("REQ@solo", index, row_type="requirement")

    assert obligations.terminals == (TerminalObligation("REQ@solo", "REQ@solo"),)


def test_an_aggregate_outcome_carries_its_constituents_instead_of_itself() -> None:
    """The middle of the chain, for the same reason: the constituents answer for the whole."""
    index = _index(
        [_e("OUT@whole"), _e("OUT@part"), _e("REQ@a")],
        [_aggregates("OUT@whole", "OUT@part"), _realizes("REQ@a", "OUT@part")],
    )

    obligations = _obligations("OUT@whole", index, row_type="outcome")

    assert obligations.missing == (), "the whole no longer owes a requirement of its own"
    assert obligations.terminals == (TerminalObligation("OUT@part", "REQ@a"),)


def test_an_aggregate_outcome_is_a_gap_when_a_constituent_has_no_requirement() -> None:
    index = _index(
        [_e("OUT@whole"), _e("OUT@bare")],
        [_aggregates("OUT@whole", "OUT@bare")],
    )

    obligations = _obligations("OUT@whole", index, row_type="outcome")

    assert obligations.missing == (MissingRequirementObligation("OUT@bare", "OUT@bare"),)
