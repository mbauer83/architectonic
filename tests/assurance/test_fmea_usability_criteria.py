"""Two of the method's task-completion criteria, as tests rather than as a walkthrough.

Both are about what a reader is offered, not about a function's return value, and both were
unreachable while the architecture graph never arrived: a safety analysis could not show a
structurally nominated row at all, and a redundancy that shares a cause is a statement no store can
make. They are here rather than in a manual checklist because each has a definite answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.assurance.fmea_architecture import (
    ArchitectureBasis,
    read_architecture_basis,
)
from src.application.assurance.fmea_rows import matrix_rows
from src.application.verification.assurance_verifier import verify_store
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.failure_modes import UNTOUCHED

DEPENDENT = "APP@1100000000.dep.the-caller"
PRIMARY = "APP@1100000001.pri.primary-provider"
STANDBY = "APP@1100000002.std.standby-provider"
SHARED = "TNO@1100000003.shr.shared-host"

PRIMARY_KEY = canonical_entity_key(PRIMARY)
STANDBY_KEY = canonical_entity_key(STANDBY)
SHARED_KEY = canonical_entity_key(SHARED)


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


@dataclass(frozen=True)
class _Connection:
    artifact_id: str
    source: str
    target: str
    conn_type: str


class _Model:
    def __init__(self, connections: list[_Connection]) -> None:
        self._connections = connections

    def list_connections(self) -> list[Any]:
        return list(self._connections)

    def list_entities(self) -> list[Any]:
        return []


class _Catalog:
    def all_connection_types(self) -> dict[str, _TypeInfo]:
        return {"archimate-serving": _TypeInfo("dependency", 4)}


def _named_by_the_analysis(store: Any) -> None:
    """Put the primary provider in scope the way the method requires: by naming it.

    The graph does not nominate rows. So a test about a usable safety analysis has to stage the one
    act that puts an element on the list, which is the act the design says a caller makes
    deliberately.
    """
    controller = str(store.create_node("control-structure-node", "Primary provider"))
    store.register_arch_ref(controller, PRIMARY, "binds-to")


def _rows(store: Any) -> list[dict[str, object]]:
    return matrix_rows(
        nodes=store.list_nodes(), edges=store.list_edges(), arch_refs=store.list_arch_refs(),
        assessments={}, basis=_redundant_pair_over_a_shared_host(),
    )


def _redundant_pair_over_a_shared_host() -> ArchitectureBasis:
    """One caller with two interchangeable providers, both standing on the same host.

    Which is the shape redundancy that is not redundancy takes: nothing in the model declares the
    pair as alternatives, and nothing declares the sharing — both are read off the graph.
    """
    return read_architecture_basis(
        _Model([
            _Connection("C1", DEPENDENT, PRIMARY, "archimate-serving"),
            _Connection("C2", DEPENDENT, STANDBY, "archimate-serving"),
            _Connection("C3", PRIMARY, SHARED, "archimate-serving"),
            _Connection("C4", STANDBY, SHARED, "archimate-serving"),
        ]),
        connection_types=_Catalog(),
    )


class TestRedundancyIsNotInferredFromCoService:
    """Two elements serving the same dependent are collaborating, not standing in for each other.

    The check exists and is tested against staged pairs; nothing feeds it real ones. Run over the
    repository this software describes it produced 3670 findings, among them pairs of a data object
    and a requirement — substitutability nobody declared. This model can say two elements stand in for
    each other, through an OR-junction in a realization relation for instance, and the check becomes
    sound once it derives from that declaration.
    """

    def test_co_serving_elements_are_not_reported_as_false_redundancy(self, unlocked_store: Any) -> None:
        codes = [
            issue.code
            for issue in verify_store(unlocked_store, basis=_redundant_pair_over_a_shared_host()).issues
        ]

        assert "W515" not in codes


class TestASafetyOnlyAnalysisWithNoSbomAnywhere:
    """No security signals, no snapshot, no vulnerability anywhere — and still fully usable."""

    def test_the_matrix_offers_rows_factors_and_a_next_action(self, unlocked_store: Any) -> None:
        _named_by_the_analysis(unlocked_store)

        rows = _rows(unlocked_store)

        assert rows, "a safety analysis must be workable with no SBOM anywhere"
        for row in rows:
            assert len(row["cells"]) == 5
            # No worst band yet, and that is correct: nobody has recorded anything against these
            # rows. What must be present is the next action, so the worklist can be worked through.
            assert row["worst_action_priority"] is None
            for cell in row["cells"]:
                assert cell["state"] == UNTOUCHED
                assert cell["next_action"]

    def test_no_surface_shows_an_empty_vulnerability_affordance(self, unlocked_store: Any) -> None:
        """An empty security section reads as "assessed, nothing found" — the opposite of the truth."""
        _named_by_the_analysis(unlocked_store)

        rows = _rows(unlocked_store)

        drafts = [str(cell["occurrence_rationale_draft"]) for row in rows for cell in row["cells"]]

        assert not any("vulnerability" in draft for draft in drafts)
        assert not any("snapshot" in draft for draft in drafts)

    def test_the_verifier_reports_nothing_about_security_snapshots(self, unlocked_store: Any) -> None:
        codes = [
            issue.code
            for issue in verify_store(unlocked_store, basis=_redundant_pair_over_a_shared_host()).issues
        ]

        assert "W513" not in codes
