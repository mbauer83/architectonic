"""Verifier tests for datatype identity / unique_keys (E338 / E337)."""

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.datatype._contributions_keys import KEY_CONSTRAINT_CONTRIBUTION
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext

_ATTRS = [
    {"id": "a1", "name": "tenant"},
    {"id": "a2", "name": "number"},
]


def _run(*, identity=None, unique_keys=None) -> list:
    classifier: dict = {"id": "CLF@1.ab.order", "attributes": _ATTRS}
    if identity is not None:
        classifier["identity"] = identity
    if unique_keys is not None:
        classifier["unique_keys"] = unique_keys
    fm = {"diagram-type": "datatype", "diagram-entities": {"classifier": [classifier]}}
    ctx = BaseDiagramVerificationContext(
        fm=fm, loc="test.puml", scope="engagement", diagram_id="DT-A",
        allowed_connections=frozenset(), allowed_entities=frozenset(), catalogs=None,
    )
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    KEY_CONSTRAINT_CONTRIBUTION.run(None, ctx, result)
    return result.issues


def _codes(issues) -> set:
    return {i.code for i in issues}


class TestIdentity:
    def test_valid_composite_identity_passes(self):
        assert _run(identity=["a1", "a2"]) == []

    def test_empty_identity_is_not_an_error(self):
        assert _run(identity=[]) == []

    @pytest.mark.parametrize(
        ("identity", "message"),
        [
            (["a1", "a1"], "duplicate"),
            (["a1", "missing"], "unknown attribute id"),
            (["a1", ""], "empty attribute"),
        ],
    )
    def test_invalid_identity_emits_e338(self, identity, message):
        issues = _run(identity=identity)
        assert _codes(issues) == {"E338"}
        assert issues[0].severity == Severity.ERROR
        assert message in issues[0].message


class TestUniqueKeys:
    def test_valid_unique_keys_pass(self):
        assert _run(unique_keys=[{"name": "k", "attribute_ids": ["a1"]}, {"attribute_ids": ["a2"]}]) == []

    @pytest.mark.parametrize(
        ("keys", "message"),
        [
            ([{"attribute_ids": []}], "at least one"),
            ([{"attribute_ids": ["a1", "a1"]}], "duplicate"),
            ([{"attribute_ids": ["missing"]}], "unknown attribute id"),
            ([{}], "at least one"),
        ],
    )
    def test_invalid_unique_key_emits_e337(self, keys, message):
        issues = _run(unique_keys=keys)
        assert _codes(issues) == {"E337"}
        assert message in issues[0].message


def test_key_codes_registered() -> None:
    from src.diagram_types.datatype import module

    codes = {
        code
        for contribution in module.diagram_verification_contributions()
        for code in contribution.diagnostic_codes
    }
    assert {"E337", "E338"} <= codes
