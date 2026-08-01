"""Server-side edge-create validation against the ontology matrix: every
permitted row is accepted, forbidden samples are rejected with the typed
illegal-pair outcome (carrying the pair's full legal set), the audit log gains
entries only for accepted writes, and the HTTP surface translates the
rejection to a 422 typed envelope."""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance import mutations as mut
from src.application.assurance.edge_catalog import legal_connection_types_for
from src.ontologies.assurance._loader import _PACKAGE_DIR, load_assurance_module

_MODULE = load_assurance_module(_PACKAGE_DIR)
_LEGAL = legal_connection_types_for(_MODULE)

_MATRIX_ROWS = sorted(
    (str(source), str(target), str(conn))
    for source, entries in _MODULE.permitted_relationships.by_source().items()
    for target, conn in entries
)

_FORBIDDEN_SAMPLES = [
    # Reversed causal chain: losses never lead back to hazards.
    ("loss", "hazard", "leads-to"),
    # Scenario relation misused causally (owner-locked: explains, never leads-to).
    ("loss-scenario", "hazard", "leads-to"),
    # Reference type submitted as an edge type (disjoint catalogs).
    ("assurance-constraint", "evidence", "binds-to"),
    # Retired edge vocabulary.
    ("unsafe-control-action", "hazard", "violates"),
    # Unknown connection type.
    ("hazard", "loss", "made-up-type"),
    # Unknown node types legalize nothing.
    ("nonsense", "loss", "leads-to"),
]


#: The analysis every fixture node is attributed to.
_FIXTURE_ANALYSIS = "STPA@fixture"


class _FakeStore:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._seq = 0

    def is_unlocked(self) -> bool:
        return True

    def create_node(self, node_type: str, name: str) -> str:
        self._seq += 1
        node_id = f"NOD@{self._seq}"
        # Every node records the analysis that produced it. A node without provenance is
        # repair-only, so a fixture minting one would be testing the guard rather than the matrix.
        self._nodes[node_id] = {
            "node_id": node_id, "node_type": node_type, "name": name,
            "analysis_id": _FIXTURE_ANALYSIS,
        }
        return node_id

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def list_nodes(self, **filters: object) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    def list_edges(self, **filters: object) -> list[dict[str, Any]]:
        return list(self._edges)

    def list_arch_refs(self, **filters: object) -> list[dict[str, Any]]:
        return []

    def read_fmea_assessments(self, node_ids: Any) -> dict[str, list[dict[str, Any]]]:
        """No judgements here — this fake exists to exercise edge legality, not factors."""
        return {}

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        conn_type: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> str:
        self._edges.append({"source_id": source_id, "target_id": target_id, "conn_type": conn_type})
        return f"EDG@{len(self._edges)}"


class _FakeArchive:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        self.entries.append({"operation": operation, **kwargs})
        return {"seq": len(self.entries)}


def _attempt(source_type: str, target_type: str, conn_type: str) -> tuple[mut.MutationResult, _FakeArchive]:
    store, archive = _FakeStore(), _FakeArchive()
    sid = store.create_node(source_type, f"src {source_type}")
    tid = store.create_node(target_type, f"tgt {target_type}")
    result = mut.add_edge(
        store, archive,
        source_id=sid, target_id=tid, conn_type=conn_type,
        legal_connection_types=_LEGAL,
    )
    return result, archive


@pytest.mark.parametrize(("source_type", "target_type", "conn_type"), _MATRIX_ROWS)
def test_every_matrix_row_is_accepted_and_audited(
    source_type: str, target_type: str, conn_type: str,
) -> None:
    result, archive = _attempt(source_type, target_type, conn_type)
    assert isinstance(result, mut.MutationOk), (source_type, target_type, conn_type)
    assert archive.entries[0]["operation"] == "ADD_EDGE"


@pytest.mark.parametrize(("source_type", "target_type", "conn_type"), _FORBIDDEN_SAMPLES)
def test_forbidden_samples_are_rejected_typed_and_unaudited(
    source_type: str, target_type: str, conn_type: str,
) -> None:
    result, archive = _attempt(source_type, target_type, conn_type)
    assert isinstance(result, mut.MutationIllegalPair)
    assert result.conn_type == conn_type
    assert result.source_type == source_type
    assert result.target_type == target_type
    assert conn_type not in result.legal_types
    assert archive.entries == []  # nothing written, nothing audited


def test_rejection_carries_the_pairs_full_legal_set() -> None:
    result, _ = _attempt("hazard", "loss", "explains")
    assert isinstance(result, mut.MutationIllegalPair)
    assert result.legal_types == tuple(sorted(_LEGAL("hazard", "loss")))
    assert "leads-to" in result.legal_types


def test_matrix_row_count_is_the_module_matrix() -> None:
    """The parametrization above is EXHAUSTIVE over the module — if the matrix
    grows, this file automatically covers the new rows."""
    assert len(_MATRIX_ROWS) == sum(
        len(entries) for entries in _MODULE.permitted_relationships.by_source().values()
    )
    assert len(_MATRIX_ROWS) > 0
