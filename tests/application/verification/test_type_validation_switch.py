from pathlib import Path

from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.datatype._contributions import (
    ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION,
    _ProjectionBasedContributions,
)
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext

_PRIMITIVES = frozenset({"String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"})


class _Candidate:
    def list_entities(self, *, artifact_type=None, domain=None, status=None) -> list:
        return []

    def list_diagrams(self, *, diagram_type=None, status=None) -> list:
        return []

    def scope_for_path(self, path: Path) -> str:
        return "engagement"


def _context(type_ref: object, *, blocking: bool = True) -> BaseDiagramVerificationContext:
    return BaseDiagramVerificationContext(
        fm={
            "artifact-id": "DT-A",
            "diagram-type": "datatype",
            "status": "draft",
            "diagram-entities": {
                "classifier": [{
                    "id": "CLF@1.ab.owner",
                    "classifier_kind": "class",
                    "attributes": [{"name": "value", "type": type_ref}],
                }],
            },
        },
        loc="test.puml",
        scope="engagement",
        diagram_id="DT-A",
        allowed_connections=frozenset(),
        allowed_entities=frozenset(),
        catalogs=None,
        type_references_blocking=blocking,
    )


def test_unresolved_type_is_blocking_when_switch_enabled() -> None:
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")

    _ProjectionBasedContributions(_PRIMITIVES).run(
        _Candidate(),
        _context({"kind": "primitive", "name": "Unknown"}),
        result,
    )

    issue = next(item for item in result.issues if item.code == "E332")
    assert issue.severity == Severity.ERROR
    assert result.valid is False


def test_type_diagnostics_are_advisory_when_switch_disabled() -> None:
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    context = _context("legacy-string", blocking=False)

    ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION.run(_Candidate(), context, result)
    _ProjectionBasedContributions(_PRIMITIVES).run(_Candidate(), context, result)

    diagnostics = [item for item in result.issues if item.code in {"E332", "E336"}]
    assert diagnostics
    assert all(item.severity == Severity.WARNING for item in diagnostics)
    assert result.valid is True


def test_settings_flag_can_disable_blocking(monkeypatch) -> None:
    from src.config.settings import datatype_type_references_blocking

    monkeypatch.setattr(
        "src.config.settings.load_settings",
        lambda: {"validation": {"datatype_type_references_blocking": False}},
    )

    assert datatype_type_references_blocking() is False
