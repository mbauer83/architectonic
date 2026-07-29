"""WU-3.1: E334 reference-impact contribution — removed classifier still referenced."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_types import VerificationResult
from src.diagram_types.datatype._contributions import (
    _find_classifier_usages,
    _ReferenceImpactContribution,
)
from src.domain.diagrams.diagram_verification import RepositoryVerificationContext

_CLF_A = "CLF@1.aa.order"
_CLF_B = "CLF@1.bb.customer"
_DT_001 = "DT@1.xx.orders"
_DT_002 = "DT@1.yy.customers"


@dataclass
class _FakeEntity:
    artifact_id: str
    artifact_type: str = "classifier"


@dataclass
class _FakeDiagram:
    artifact_id: str
    diagram_type: str = "datatype"
    extra: dict = field(default_factory=dict)


@dataclass
class _FakeRepo:
    entities: list[_FakeEntity] = field(default_factory=list)
    diagrams: list[_FakeDiagram] = field(default_factory=list)

    def list_entities(self, *, artifact_type: str | None = None, **_: object) -> list[_FakeEntity]:
        if artifact_type is None:
            return list(self.entities)
        return [e for e in self.entities if e.artifact_type == artifact_type]

    def list_diagrams(self, *, diagram_type: str | None = None, **_: object) -> list[_FakeDiagram]:
        if diagram_type is None:
            return list(self.diagrams)
        return [d for d in self.diagrams if d.diagram_type == diagram_type]

    def scope_for_path(self, path: Path) -> str:
        return "engagement"


def _ctx(committed: _FakeRepo, candidate: _FakeRepo) -> RepositoryVerificationContext:
    return RepositoryVerificationContext(
        committed=committed,
        candidate=candidate,
        location="/repo",
    )


def _run(committed: _FakeRepo, candidate: _FakeRepo) -> VerificationResult:
    result = VerificationResult(path=Path("/repo"), file_type="diagram")
    ctx = _ctx(committed, candidate)
    _ReferenceImpactContribution().run(ctx, result)
    return result


def _diagram_with_ref(artifact_id: str, clf_id: str, ref_id: str, attr_name: str = "type") -> _FakeDiagram:
    return _FakeDiagram(
        artifact_id=artifact_id,
        extra={
            "diagram-entities": {
                "classifier": [
                    {
                        "id": clf_id,
                        "attributes": [{"name": attr_name, "type": {"kind": "classifier", "id": ref_id}}],
                    }
                ]
            }
        },
    )


# ── _find_classifier_usages ───────────────────────────────────────────────────


def test_find_usages_empty_candidate():
    candidate = _FakeRepo(diagrams=[])
    assert _find_classifier_usages(candidate, _CLF_A) == []


def test_find_usages_no_matching_ref():
    candidate = _FakeRepo(diagrams=[_diagram_with_ref(_DT_001, "CLF@1.x.line", _CLF_B)])
    assert _find_classifier_usages(candidate, _CLF_A) == []


def test_find_usages_single_match():
    candidate = _FakeRepo(diagrams=[_diagram_with_ref(_DT_001, "CLF@1.x.line", _CLF_A, "lineType")])
    usages = _find_classifier_usages(candidate, _CLF_A)
    assert len(usages) == 1
    assert usages[0] == (_DT_001, "CLF@1.x.line", "lineType")


def test_find_usages_multiple_diagrams():
    d1 = _diagram_with_ref(_DT_001, "CLF@1.a.x", _CLF_A)
    d2 = _diagram_with_ref(_DT_002, "CLF@1.b.y", _CLF_A)
    candidate = _FakeRepo(diagrams=[d1, d2])
    usages = _find_classifier_usages(candidate, _CLF_A)
    assert {u[0] for u in usages} == {_DT_001, _DT_002}


def test_find_usages_ignores_primitive_refs():
    candidate = _FakeRepo(
        diagrams=[
            _FakeDiagram(
                artifact_id=_DT_001,
                extra={
                    "diagram-entities": {
                        "classifier": [
                            {
                                "id": "CLF@1.x.a",
                                "attributes": [{"name": "n", "type": {"kind": "primitive", "name": "String"}}],
                            }
                        ]
                    }
                },
            )
        ]
    )
    assert _find_classifier_usages(candidate, _CLF_A) == []


def test_find_usages_diagram_without_entities():
    candidate = _FakeRepo(diagrams=[_FakeDiagram(artifact_id=_DT_001, extra={})])
    assert _find_classifier_usages(candidate, _CLF_A) == []


# ── _ReferenceImpactContribution ──────────────────────────────────────────────


def test_no_removals_no_issues():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A), _FakeEntity(_CLF_B)])
    candidate = _FakeRepo(entities=[_FakeEntity(_CLF_A), _FakeEntity(_CLF_B)])
    result = _run(committed, candidate)
    assert result.valid


def test_removal_without_usages_no_issues():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A), _FakeEntity(_CLF_B)])
    candidate = _FakeRepo(entities=[_FakeEntity(_CLF_B)], diagrams=[])
    result = _run(committed, candidate)
    assert result.valid


def test_removal_with_usage_emits_e334():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A), _FakeEntity(_CLF_B)])
    candidate = _FakeRepo(
        entities=[_FakeEntity(_CLF_B)],
        diagrams=[_diagram_with_ref(_DT_002, "CLF@1.b.y", _CLF_A, "orderType")],
    )
    result = _run(committed, candidate)
    assert not result.valid
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "E334"
    assert _CLF_A in issue.message
    assert "orderType" in issue.message


def test_e334_includes_details():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A)])
    candidate = _FakeRepo(
        entities=[],
        diagrams=[_diagram_with_ref(_DT_002, "CLF@1.b.y", _CLF_A)],
    )
    result = _run(committed, candidate)
    assert not result.valid
    details = result.issues[0].details
    assert details is not None
    assert details["removed_id"] == _CLF_A
    assert len(details["usages"]) == 1
    assert details["usages"][0]["diagram_id"] == _DT_002


def test_multiple_removed_classifiers_separate_issues():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A), _FakeEntity(_CLF_B)])
    candidate = _FakeRepo(
        entities=[],
        diagrams=[
            _diagram_with_ref(_DT_001, "CLF@1.x.a", _CLF_A),
            _diagram_with_ref(_DT_002, "CLF@1.y.b", _CLF_B),
        ],
    )
    result = _run(committed, candidate)
    codes = [i.code for i in result.issues]
    assert codes.count("E334") == 2


def test_removal_referenced_by_multiple_attrs():
    candidate = _FakeRepo(
        diagrams=[
            _FakeDiagram(
                artifact_id=_DT_001,
                extra={
                    "diagram-entities": {
                        "classifier": [
                            {
                                "id": "CLF@1.x.a",
                                "attributes": [
                                    {"name": "field1", "type": {"kind": "classifier", "id": _CLF_A}},
                                    {"name": "field2", "type": {"kind": "classifier", "id": _CLF_A}},
                                ],
                            }
                        ]
                    }
                },
            )
        ]
    )
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A)])
    result = _run(committed, candidate)
    assert not result.valid
    details = result.issues[0].details
    assert details is not None
    assert len(details["usages"]) == 2


def test_e334_location_is_repo_path():
    committed = _FakeRepo(entities=[_FakeEntity(_CLF_A)])
    candidate = _FakeRepo(
        entities=[],
        diagrams=[_diagram_with_ref(_DT_001, "CLF@1.x.a", _CLF_A)],
    )
    result = _run(committed, candidate)
    assert result.issues[0].location == "/repo"


def test_empty_committed_no_issues():
    committed = _FakeRepo(entities=[])
    candidate = _FakeRepo(entities=[], diagrams=[_diagram_with_ref(_DT_001, "CLF@1.x.a", _CLF_A)])
    result = _run(committed, candidate)
    assert result.valid


@pytest.mark.parametrize("code", ["E334"])
def test_diagnostic_codes_declared(code: str):
    assert code in _ReferenceImpactContribution.diagnostic_codes
