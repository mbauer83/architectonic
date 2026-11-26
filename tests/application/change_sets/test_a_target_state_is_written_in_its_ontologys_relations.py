"""A target state is written in the relations its ontology declares, not in names the change-set core spells.

The core named `archimate-association` and `archimate-aggregation` itself, so a non-ArchiMate ontology could
not express a target state and an ontology rename would have broken it silently. The ArchiMate module now
declares them (`connections.yaml`, `target_state_relations`), the module catalogue answers the one
declaration, and `target_plan`, `move_into_baseline` and `withdrawal_of` take them as an argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from src.application.change_sets.base import BaseValue
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import AddConnection, EditEntity, RemoveConnection
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.target_state import target_plan
from src.application.change_sets.target_withdraw import withdrawal_of
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.domain.ontology_representation.target_state_relations import TargetStateRelations
from src.infrastructure.app_bootstrap import get_module_registry

#: A vocabulary that is not ArchiMate's, so a name the core still spelled would show.
_OWN = TargetStateRelations(trace="own-traces", holds="own-holds")
_LEDGER = "APP@1.a.ledger"


class TestTheDeclaration:
    def test_an_ontology_that_declares_none_answers_none(self) -> None:
        assert TargetStateRelations.from_mapping({"connection_types": {}}) is None

    def test_the_names_are_read_as_the_ontology_spells_them(self) -> None:
        declared = TargetStateRelations.from_mapping(
            {"target_state_relations": {"trace": "association", "holds": "aggregation"}},
            named=lambda short: f"onto-{short}",
        )
        assert declared == TargetStateRelations(trace="onto-association", holds="onto-aggregation")

    def test_a_declaration_missing_a_relation_is_refused(self) -> None:
        with pytest.raises(ValueError, match="trace"):
            TargetStateRelations.from_mapping({"target_state_relations": {"holds": "aggregation"}})


@dataclass(frozen=True)
class _Ontology:
    name: str
    target_state_relations: TargetStateRelations | None


def _module(ontology: _Ontology) -> OntologyModule:
    """A stand-in answering the one question the catalogue asks of an ontology here."""
    return cast(OntologyModule, ontology)


def _catalog(*ontologies: _Ontology) -> ModuleCatalog:
    return ModuleCatalog({ontology.name: _module(ontology) for ontology in ontologies}, {})


class TestTheCatalogue:
    def test_the_one_declaration_is_the_answer(self) -> None:
        catalog = _catalog(_Ontology("one", _OWN), _Ontology("other", None))
        assert catalog.target_state_relations() == _OWN

    def test_no_declaration_answers_none(self) -> None:
        assert _catalog(_Ontology("other", None)).target_state_relations() is None

    def test_two_declarations_are_refused_as_ambiguous(self) -> None:
        with pytest.raises(ValueError, match="More than one"):
            _catalog(_Ontology("one", _OWN), _Ontology("two", _OWN)).target_state_relations()

    def test_the_registry_delegates_to_its_catalogue(self) -> None:
        registry = ModuleRegistry()
        registry.register_ontology(_module(_Ontology("one", _OWN)))
        assert registry.target_state_relations() == _OWN


def test_archimate_declares_relations_it_holds() -> None:
    relations = get_module_registry().target_state_relations()
    assert relations == TargetStateRelations(trace="archimate-association", holds="archimate-aggregation")
    connection_types = get_module_registry().all_connection_types()
    assert ConnectionTypeName(relations.trace) in connection_types
    assert ConnectionTypeName(relations.holds) in connection_types


def _renaming() -> CandidateArchitecture:
    rename = EditEntity(_LEDGER, "name", "Ledger service", BaseValue("Ledger"))
    return CandidateArchitecture("CAND@1.b", "Ledger", "", "draft", ChangeSet((rename,), "r1"))


_LIVE = RecordedReading(
    entities={_LEDGER: {"name": "Ledger", "artifact_type": "application-component", "group": "core"}},
)


def _allocate(kind: str, name: str) -> str:
    return f"{kind.upper()[:3]}@1.{abs(hash((kind, name))) % 10_000}.x"


def _relations_written(operations: Any) -> set[str]:
    return {op.address.connection_type for op in operations if isinstance(op, AddConnection)}


def test_a_target_state_is_traced_and_held_by_the_relations_handed_in() -> None:
    plan = target_plan(
        _renaming(), _LIVE, revision="r1", allocate=_allocate, permits=lambda *_: True, relations=_OWN,
    )
    assert _relations_written(plan.changes.operations) == {"own-traces", "own-holds"}


def test_withdrawing_cuts_what_it_wrote_in_the_relations_it_is_told_of() -> None:
    """Withdrawal tells the target state's own relations from ones written since by the same relations it
    was written with: in any other vocabulary the plateaus' and the gap's own relations read as foreign."""
    plan = target_plan(
        _renaming(), _LIVE, revision="r1", allocate=_allocate, permits=lambda *_: True, relations=_OWN,
    )
    written = [op.address for op in plan.shown if isinstance(op, AddConnection)]
    live = RecordedReading(
        entities={**_LIVE.entities, **{ref: {"name": ref, "group": "core"} for ref in plan.state.written}},
        connections={address: {} for address in written},
    )

    withdrawal = withdrawal_of(_renaming(), plan.state, live, revision="r2", relations=_OWN)

    assert withdrawal.foreign == ()
    cut = {op.address for op in withdrawal.changes.operations if isinstance(op, RemoveConnection)}
    assert cut == set(written)
