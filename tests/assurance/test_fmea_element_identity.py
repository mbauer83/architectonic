"""One architecture element is one element, whichever spelling of its id reached the store.

An entity id may carry its rename-volatile slug or not, and both forms are legitimate: the GUI
navigates by the full `PREFIX@epoch.random.slug` id, MCP callers and scripts usually pass the short
one. Every join in this feature crosses two stores that do not agree on which they hold — the
confidential store's architecture references on one side, the architecture graph's own relationship
endpoints on the other — and each match is a string comparison.

Compared raw, the failure is never an error. The same element is nominated twice under two names;
its entity page reports no failure modes while the matrix shows several; a redundant pair looks
redundant because the shared dependency underneath them was split in half; and the verifier reports
a gap that the analysis has, in fact, already closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.application.assurance.fmea_effect_suggestion import suggest_effects
from src.application.assurance.fmea_rows import candidates, matrix_rows
from src.application.verification.assurance_verifier import verify_store
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.fmea_structural_signals import sole_providers, typed_edges

SHORT = "APP@1777293133.OYEmP1"
FULL = "APP@1777293133.OYEmP1.architecture-backend"


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


def _node(node_id: str, node_type: str, **fields: object) -> dict[str, Any]:
    return {"node_id": node_id, "node_type": node_type, "name": node_id, **fields}


def _ref(node_id: str, element_id: str) -> dict[str, Any]:
    return {"assurance_node_id": node_id, "arch_artifact_id": element_id, "ref_type": "binds-to"}


class TestTheCanonicalKey:
    def test_the_two_forms_agree(self) -> None:
        assert canonical_entity_key(FULL) == canonical_entity_key(SHORT) == SHORT

    def test_a_diagram_hosted_node_id_is_left_alone(self) -> None:
        """Truncating this at its last dot would produce an id that names nothing."""
        hosted = "CS@1781183304.5Ezxuv.stpa-control-structure-store-access#nodes/csn-cred"

        assert canonical_entity_key(hosted) == hosted

    def test_a_synthetic_anchor_is_left_alone(self) -> None:
        assert canonical_entity_key("not-an-id.at.all") == "not-an-id.at.all"


class TestTheCandidateSet:
    def test_an_element_bound_under_both_forms_is_one_candidate(self) -> None:
        nodes = [_node("CSN@1", "control-structure-node"), _node("CSN@2", "control-structure-node")]

        found = candidates(nodes=nodes, arch_refs=[_ref("CSN@1", FULL), _ref("CSN@2", SHORT)])

        assert [c.element_id for c in found] == [SHORT]

    def test_a_failure_mode_lands_in_the_row_bound_under_the_other_form(self) -> None:
        """The analyst binds the control-structure node one way and the failure mode the other.
        Unnormalised the row stays empty, and the surface asks for work already done."""
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type="no-function"),
        ]

        rows = matrix_rows(
            nodes=nodes,
            edges=[],
            arch_refs=[_ref("CSN@1", FULL), _ref("FMD@1", SHORT)],
            assessments={},
        )

        assert len(rows) == 1
        recorded = [c for c in rows[0]["cells"] if c["state"] != "untouched"]  # type: ignore[union-attr]
        assert len(recorded) == 1


class TestTheStructuralGraph:
    def test_endpoints_in_either_form_are_one_node(self) -> None:
        """A dependent reaching the same provider under two spellings has two providers on paper
        and one in fact — so it is a sole provider, and the raw comparison says it is not."""
        connections = [
            {"artifact_id": "C1", "source": "APP@1.aaa.dependent",
             "target": FULL, "connection_type": "archimate-serving"},
            {"artifact_id": "C2", "source": "APP@1.aaa",
             "target": SHORT, "connection_type": "archimate-serving"},
        ]
        edges = typed_edges(connections, {"archimate-serving": _TypeInfo("dependency", 4)})

        assert sole_providers(edges) == {SHORT: ("APP@1.aaa",)}

    def test_a_hazard_is_suggested_through_a_neighbour_bound_under_the_other_form(self) -> None:
        connections = [
            {"artifact_id": "C1", "source": "APP@2.bbb.caller", "target": FULL,
             "connection_type": "archimate-serving"},
        ]
        edges = typed_edges(connections, {"archimate-serving": _TypeInfo("dependency", 4)})
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("UCA@1", "unsafe-control-action"),
            _node("HAZ@1", "hazard"),
        ]
        assurance_edges = [
            {"edge_id": "E1", "source_id": "UCA@1", "conn_type": "by-controller",
             "target_id": "CSN@1"},
            {"edge_id": "E2", "source_id": "UCA@1", "conn_type": "leads-to", "target_id": "HAZ@1"},
        ]

        found = suggest_effects(
            "APP@2.bbb", nodes=nodes, arch_refs=[_ref("CSN@1", SHORT)],
            edges=edges, assurance_edges=assurance_edges,
        )

        assert [s.hazard_id for s in found] == ["HAZ@1"]


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    built = SQLCipherAssuranceStore(db_path)
    built.unlock()
    yield built
    built.lock()


class TestTheVerifier:
    def test_an_element_is_reported_once_however_its_id_was_spelled(self, store: Any) -> None:
        for index, form in enumerate((FULL, SHORT)):
            node_id = str(store.create_node("control-structure-node", f"Controller {index}"))
            store.register_arch_ref(node_id, form, "binds-to")

        reported = [i for i in verify_store(store).issues if i.code == "W510"]

        assert len(reported) == 1

    def test_examining_the_element_clears_the_finding(self, store: Any) -> None:
        """Bound the other way round from the control-structure node — the case that previously
        left the analyst with a finding no amount of further analysis could close."""
        controller = str(store.create_node("control-structure-node", "Controller"))
        store.register_arch_ref(controller, FULL, "binds-to")
        failure_mode = str(store.create_node("failure-mode", "Backend stops serving requests"))
        store.register_arch_ref(failure_mode, SHORT, "binds-to")

        assert "W510" not in [i.code for i in verify_store(store).issues]
