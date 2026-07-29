"""Regression tests for the §3.2 bidirectional consistency verifier rules.

Forward (E330): dt-* edge between two DOB-bound classifiers with no backing
    connection binding → error.
Reverse (E331): bound backing connection with wrong relationship_kind or
    direction → error.
Clean: correct binding clears all errors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_rules_datatype import check_datatype_backing_consistency
from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalogs():
    return build_runtime_catalogs(get_module_registry())


def _result() -> VerificationResult:
    return VerificationResult(path=Path("diag.puml"), file_type="diagram")


_DOB_A = "DOB@111.aaaa.alpha"
_DOB_B = "DOB@222.bbbb.beta"
_DOB_C = "DOB@333.cccc.gamma"

# Canonical model connection IDs (format: src---tgt@@type)
_ASSOC_AB = f"{_DOB_A}---{_DOB_B}@@archimate-association"
_SPEC_AB = f"{_DOB_A}---{_DOB_B}@@archimate-specialization"
_AGGR_AB = f"{_DOB_A}---{_DOB_B}@@archimate-aggregation"
_SPEC_BA = f"{_DOB_B}---{_DOB_A}@@archimate-specialization"  # inverted direction


def _fm_datatype(*, connections, bindings=None):
    """Minimal datatype diagram frontmatter with two classifiers."""
    return {
        "diagram-type": "datatype",
        "diagram-entities": {
            "classifier": [
                {"id": "cls_a", "classifier_kind": "class"},
                {"id": "cls_b", "classifier_kind": "class"},
            ]
        },
        "connections": connections,
        "bindings": bindings or [],
    }


def _entity_binding(binding_id, subject_elem_id, target_entity_id):
    return {
        "id": binding_id,
        "subject": {"kind": "entity", "id": subject_elem_id},
        "correspondence_kind": "represents",
        "target": {"entity_id": target_entity_id},
    }


def _connection_binding(binding_id, subject_conn_elem_id, model_conn_id):
    return {
        "id": binding_id,
        "subject": {"kind": "connection", "id": subject_conn_elem_id},
        "correspondence_kind": "represents",
        "target": {"connection_id": model_conn_id},
    }


def _both_dob_bound_bindings():
    return [
        _entity_binding("b_a", "cls_a", _DOB_A),
        _entity_binding("b_b", "cls_b", _DOB_B),
    ]


# ---------------------------------------------------------------------------
# Forward error (E330) — missing backing connection
# ---------------------------------------------------------------------------


class TestForwardError:
    def test_dt_association_no_binding_emits_e330(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings(),
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_ASSOC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        errors = [i for i in r.issues if i.code == "E330"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_e330_details_have_required_fields(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings(),
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_ASSOC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        e330 = next(i for i in r.issues if i.code == "E330")
        assert e330.details is not None
        assert e330.details["dob_source"] == _DOB_A
        assert e330.details["dob_target"] == _DOB_B
        assert e330.details["dt_conn_id"] == "c1"
        assert e330.details["dt_relationship_kind"] == "association"
        assert "permitted_backing_kinds" in e330.details
        assert "association" in e330.details["permitted_backing_kinds"]

    def test_e330_permitted_backing_kinds_ontology_derived(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-generalization", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings(),
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        e330 = next(i for i in r.issues if i.code == "E330")
        assert e330.details["dt_relationship_kind"] == "generalization"
        assert "generalization" in e330.details["permitted_backing_kinds"]

    def test_actions_present_for_e330(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings(),
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        e330 = next(i for i in r.issues if i.code == "E330")
        assert e330.actions is not None
        assert len(e330.actions) >= 1
        assert e330.actions[0]["type"] == "create_connection"


# ---------------------------------------------------------------------------
# Clean case — correct binding clears the error
# ---------------------------------------------------------------------------


class TestCleanCase:
    def test_dt_association_with_archimate_association_backing_is_clean(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _ASSOC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_ASSOC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not any(i.code in ("E330", "E331") for i in r.issues)

    def test_dt_association_reverse_direction_also_clean(self, catalogs) -> None:
        assoc_ba = f"{_DOB_B}---{_DOB_A}@@archimate-association"
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", assoc_ba),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {assoc_ba}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not any(i.code in ("E330", "E331") for i in r.issues)

    def test_dt_generalization_same_direction_clean(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-generalization", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _SPEC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_SPEC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not any(i.code in ("E330", "E331") for i in r.issues)

    def test_dt_composition_with_aggregation_backing_is_clean(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-composition", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _AGGR_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_AGGR_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not any(i.code in ("E330", "E331") for i in r.issues)


# ---------------------------------------------------------------------------
# Reverse error (E331) — bound but non-corresponding backing
# ---------------------------------------------------------------------------


class TestReverseError:
    def test_specialization_backing_with_dt_association_emits_e331(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _SPEC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_SPEC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        errors = [i for i in r.issues if i.code == "E331"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_e331_details_carry_both_relationship_kinds(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _SPEC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_SPEC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        e331 = next(i for i in r.issues if i.code == "E331")
        assert e331.details is not None
        assert e331.details["dt_relationship_kind"] == "association"
        assert e331.details["backing_relationship_kind"] == "generalization"

    def test_inverse_dt_generalization_with_forward_specialization_emits_e331(self, catalogs) -> None:
        # specialization goes A→B but dt-generalization goes B→A (inverse direction)
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-generalization", "source": "cls_b", "target": "cls_a"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _SPEC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_SPEC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        errors = [i for i in r.issues if i.code == "E331"]
        assert len(errors) == 1

    def test_e331_no_hardcoded_list(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-generalization", "source": "cls_a", "target": "cls_b"}],
            bindings=_both_dob_bound_bindings() + [
                _connection_binding("b_c1", "c1", _ASSOC_AB),
            ],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, {_ASSOC_AB}, catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        e331 = next(i for i in r.issues if i.code == "E331")
        # permitted_backing_kinds comes from admissible_backing_kinds (ontology-derived)
        assert "generalization" in e331.details["permitted_backing_kinds"]
        assert "association" not in e331.details["permitted_backing_kinds"]


# ---------------------------------------------------------------------------
# Unbound classifiers — rule skips
# ---------------------------------------------------------------------------


class TestUnboundClassifiers:
    def test_only_one_end_bound_no_error(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=[_entity_binding("b_a", "cls_a", _DOB_A)],  # cls_b unbound
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not any(i.code in ("E330", "E331") for i in r.issues)

    def test_neither_end_bound_no_error(self, catalogs) -> None:
        fm = _fm_datatype(
            connections=[{"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}],
            bindings=[],
        )
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not r.issues


# ---------------------------------------------------------------------------
# Non-datatype diagrams — rule skips
# ---------------------------------------------------------------------------


class TestNonDatatypeDiagram:
    def test_sequence_diagram_not_checked(self, catalogs) -> None:
        fm = {
            "diagram-type": "sequence",
            "connections": [
                {"id": "c1", "conn_type": "dt-association", "source": "cls_a", "target": "cls_b"}
            ],
            "bindings": _both_dob_bound_bindings(),
        }
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not r.issues

    def test_missing_diagram_type_not_checked(self, catalogs) -> None:
        fm = {"connections": []}
        r = _result()
        check_datatype_backing_consistency(
            fm, set(), catalogs.ontology, catalogs.diagram_types, r, "diag.puml"
        )
        assert not r.issues
