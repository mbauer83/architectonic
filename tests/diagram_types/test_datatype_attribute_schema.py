"""WU-1.2 acceptance: E336 — discriminated-union attribute type ref validation.

Acceptance criteria:
- {kind:primitive,name:String} passes
- {kind:classifier,id:CLF@...} passes
- Absent type field passes (optional)
- String type, bad kind, wrong keys, bad id pattern → E336
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.datatype._contributions import ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext


def _ctx(fm: dict) -> BaseDiagramVerificationContext:
    return BaseDiagramVerificationContext(
        fm=fm,
        loc="test.puml",
        scope="engagement",
        diagram_id="DT-test",
        allowed_connections=frozenset(),
        allowed_entities=frozenset(),
        catalogs=None,
    )


def _run(fm: dict) -> list:
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION.run(None, _ctx(fm), result)
    return [i for i in result.issues if i.code == "E336"]


def _fm(attrs: list) -> dict:
    return {
        "diagram-type": "datatype",
        "diagram-entities": {
            "classifier": [{"id": "CLF@1.ab.x", "classifier_kind": "class", "attributes": attrs}]
        },
    }


# ---------------------------------------------------------------------------
# Pass cases
# ---------------------------------------------------------------------------


def test_no_type_field_passes() -> None:
    """Attribute without a type field is valid (optional type annotation)."""
    assert _run(_fm([{"name": "foo"}])) == []


def test_primitive_type_passes() -> None:
    """Valid primitive type ref passes."""
    assert _run(_fm([{"name": "x", "type": {"kind": "primitive", "name": "String"}}])) == []


def test_classifier_type_passes() -> None:
    """Valid classifier type ref with well-formed id passes."""
    assert _run(_fm([{"name": "x", "type": {"kind": "classifier", "id": "CLF@1234.Ab.order"}}])) == []


def test_no_classifiers() -> None:
    """No classifiers → no errors."""
    assert _run({"diagram-type": "datatype", "diagram-entities": {"classifier": []}}) == []


def test_no_diagram_entities() -> None:
    """Missing diagram-entities → no errors."""
    assert _run({}) == []


def test_null_type_field_passes() -> None:
    """Explicit null type field is treated as absent → valid."""
    assert _run(_fm([{"name": "x", "type": None}])) == []


# ---------------------------------------------------------------------------
# Fail cases
# ---------------------------------------------------------------------------


def test_string_type_fails() -> None:
    """Old-style string type → E336 (must be a tagged dict)."""
    issues = _run(_fm([{"name": "x", "type": "String"}]))
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert issues[0].code == "E336"


def test_primitive_missing_name_fails() -> None:
    """Primitive type without 'name' → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "primitive"}}]))
    assert issues


def test_primitive_empty_name_fails() -> None:
    """Primitive type with empty 'name' → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "primitive", "name": ""}}]))
    assert issues


def test_primitive_with_id_fails() -> None:
    """Primitive type with 'id' key → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "primitive", "name": "X", "id": "CLF@1.a.b"}}]))
    assert issues


def test_primitive_extra_keys_fail() -> None:
    """Primitive type with extra keys → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "primitive", "name": "X", "foo": "bar"}}]))
    assert issues


def test_classifier_bad_id_fails() -> None:
    """Classifier type with malformed id → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "classifier", "id": "not-valid"}}]))
    assert issues


def test_classifier_missing_id_fails() -> None:
    """Classifier type without 'id' → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "classifier"}}]))
    assert issues


def test_classifier_with_name_fails() -> None:
    """Classifier type with 'name' key → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "classifier", "id": "CLF@1.a.b", "name": "X"}}]))
    assert issues


def test_classifier_extra_keys_fail() -> None:
    """Classifier type with extra keys → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "classifier", "id": "CLF@1.a.b", "foo": "bar"}}]))
    assert issues


def test_unknown_kind_fails() -> None:
    """Unknown kind → E336."""
    issues = _run(_fm([{"name": "x", "type": {"kind": "unknown"}}]))
    assert issues


def test_integer_type_fails() -> None:
    """Non-dict type (integer) → E336."""
    issues = _run(_fm([{"name": "x", "type": 42}]))  # type: ignore[list-item]
    assert issues


# ---------------------------------------------------------------------------
# Registration check
# ---------------------------------------------------------------------------


def test_e336_registered_in_datatype_module() -> None:
    """The datatype module exposes a contribution with diagnostic_codes including 'E336'."""
    from src.diagram_types.datatype import module as dt_module  # noqa: PLC0415
    all_codes = {code for c in dt_module.diagram_verification_contributions() for code in c.diagnostic_codes}
    assert "E336" in all_codes
