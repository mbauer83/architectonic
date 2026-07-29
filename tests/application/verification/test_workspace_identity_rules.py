"""WU-0.6 acceptance: workspace-id uniqueness (E335) and format checks.

Acceptance criteria:
- Duplicate workspace id → single E335 (not per diagram)
- Malformed id → error from validate_workspace_entity_ids
- Classifier id cannot change on edit (immutability by set comparison)
- E335 fires for cross-diagram id conflicts only; clean repo → no E335
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.verification._workspace_identity_rules import (
    WorkspaceIdUniquenessContribution,
    validate_workspace_entity_ids,
)
from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.domain.diagrams.diagram_verification import RepositoryVerificationContext
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord

# ---------------------------------------------------------------------------
# Helpers — stub candidate repos and modules
# ---------------------------------------------------------------------------


def _entity(artifact_id: str, host_diagram_id: str, artifact_type: str = "classifier") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name="E",
        version="0.1.0",
        status="active",
        domain="datatype",
        subdomain=artifact_type,
        path=Path("/fake"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="E",
        display_alias=artifact_id,
        host_diagram_id=host_diagram_id,
    )


class _StubRepo:
    def __init__(self, entities: list[EntityRecord] | None = None) -> None:
        self._e: dict[str, EntityRecord] = {e.artifact_id: e for e in (entities or [])}

    def get_entity(self, aid: str) -> EntityRecord | None:
        return self._e.get(aid)

    def get_diagram(self, aid: str) -> DiagramRecord | None:
        return None

    def list_entities(self, *, artifact_type=None, domain=None, status=None) -> list[EntityRecord]:
        return [
            e for e in self._e.values()
            if (artifact_type is None or e.artifact_type == artifact_type)
        ]

    def list_diagrams(self, *, diagram_type=None, status=None) -> list[DiagramRecord]:
        return []

    def scope_for_path(self, path: Path) -> Literal["engagement", "enterprise", "unknown"]:
        return "engagement"


class _StubUiCfg:
    def __init__(self, entity_type: str, identity_scope: str = "workspace", id_prefix: str | None = "CLF") -> None:
        self.entity_type = entity_type
        self.identity_scope = identity_scope
        self.id_prefix = id_prefix


class _StubUiConfig:
    def __init__(self, dot: list | None = None) -> None:
        self.diagram_only_types = dot or []


class _StubModule:
    def __init__(self, entity_types: list[str] | None = None) -> None:
        _types = entity_types or ["classifier"]
        self.ui_config = _StubUiConfig([
            _StubUiCfg(et) for et in _types
        ])


class _StubCatalogs:
    def __init__(self, ws_types: list[str] | None = None) -> None:
        self._ws_types = ws_types or ["classifier"]

    def all_diagram_types(self) -> dict:
        return {"datatype": _StubModule(self._ws_types)}

    @property
    def diagram_types(self) -> "_StubCatalogsDT":
        return _StubCatalogsDT(self)


class _StubCatalogsDT:
    def __init__(self, parent: _StubCatalogs) -> None:
        self._p = parent

    def all_diagram_types(self) -> dict:
        return self._p.all_diagram_types()


def _make_ctx(
    committed: _StubRepo,
    candidate: _StubRepo,
    catalogs: _StubCatalogs | None = None,
) -> RepositoryVerificationContext:
    return RepositoryVerificationContext(
        committed=committed,
        candidate=candidate,
        location="/fake/repo",
        catalogs=catalogs or _StubCatalogs(),
    )


# ---------------------------------------------------------------------------
# E335: cross-diagram id conflict
# ---------------------------------------------------------------------------


def test_e335_fires_for_cross_diagram_conflict():
    """E335 when candidate entity's host_diagram_id differs from committed."""
    committed = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])
    candidate = _StubRepo([_entity("CLF@1.ab.x", "DT-B")])  # same id, different diagram
    ctx = _make_ctx(committed, candidate)
    result = VerificationResult(path=Path("/fake"), file_type="diagram")

    contrib = WorkspaceIdUniquenessContribution()
    contrib.run(ctx, result)

    errors = [i for i in result.issues if i.code == "E335"]
    assert len(errors) == 1
    assert errors[0].severity == Severity.ERROR
    assert "CLF@1.ab.x" in errors[0].message


def test_e335_single_error_per_id():
    """Only one E335 per conflicting id, never duplicated."""
    committed = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])
    candidate = _StubRepo([_entity("CLF@1.ab.x", "DT-B"), _entity("CLF@1.cd.y", "DT-B")])
    ctx = _make_ctx(committed, candidate)
    result = VerificationResult(path=Path("/fake"), file_type="diagram")

    contrib = WorkspaceIdUniquenessContribution()
    contrib.run(ctx, result)

    e335_codes = [i for i in result.issues if i.code == "E335"]
    assert len(e335_codes) == 1  # only CLF@1.ab.x conflicts; CLF@1.cd.y is new → no conflict


def test_e335_no_fire_same_diagram():
    """No E335 when committed and candidate entity have the same host_diagram_id."""
    committed = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])
    candidate = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])  # same diagram
    ctx = _make_ctx(committed, candidate)
    result = VerificationResult(path=Path("/fake"), file_type="diagram")

    WorkspaceIdUniquenessContribution().run(ctx, result)

    assert not result.issues


def test_e335_no_fire_new_entity():
    """No E335 when the entity is new (not in committed state)."""
    committed = _StubRepo()
    candidate = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])
    ctx = _make_ctx(committed, candidate)
    result = VerificationResult(path=Path("/fake"), file_type="diagram")

    WorkspaceIdUniquenessContribution().run(ctx, result)

    assert not result.issues


def test_e335_no_fire_when_no_catalogs():
    """E335 contribution skips gracefully when catalogs is None."""
    committed = _StubRepo([_entity("CLF@1.ab.x", "DT-A")])
    candidate = _StubRepo([_entity("CLF@1.ab.x", "DT-B")])
    ctx = RepositoryVerificationContext(
        committed=committed, candidate=candidate, location="/fake", catalogs=None
    )
    result = VerificationResult(path=Path("/fake"), file_type="diagram")

    WorkspaceIdUniquenessContribution().run(ctx, result)

    assert not result.issues


# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------


def test_validate_format_valid_id_passes():
    """CLF@1234.AbCd.customer is valid and passes format check."""
    module = _StubModule()
    errors = validate_workspace_entity_ids(
        {"classifier": [{"id": "CLF@1234.AbCd.customer", "label": "C"}]},
        module,
    )
    assert errors == []


def test_validate_format_missing_epoch_fails():
    """CLF@ without epoch component is rejected."""
    module = _StubModule()
    errors = validate_workspace_entity_ids(
        {"classifier": [{"id": "CLF@abc.def", "label": "C"}]},
        module,
    )
    assert errors  # at least one error


def test_validate_format_wrong_prefix_fails():
    """An id with the wrong prefix (BOB@ instead of CLF@) is rejected."""
    module = _StubModule()
    errors = validate_workspace_entity_ids(
        {"classifier": [{"id": "BOB@1234.ab.x", "label": "C"}]},
        module,
    )
    assert errors


def test_validate_format_existing_id_skipped():
    """An id already in committed_ids is not re-validated (immutability: existing ids are fine)."""
    module = _StubModule()
    errors = validate_workspace_entity_ids(
        {"classifier": [{"id": "CLF@bad", "label": "C"}]},
        module,
        committed_ids={"CLF@bad"},  # already committed → skip format check
    )
    assert errors == []


def test_validate_format_empty_id_skipped():
    """Empty id is not validated (allocator will assign one)."""
    module = _StubModule()
    errors = validate_workspace_entity_ids(
        {"classifier": [{"id": "", "label": "C"}]},
        module,
    )
    assert errors == []


def test_validate_format_diagram_scoped_entity_ignored():
    """Diagram-scoped entity types are not checked by validate_workspace_entity_ids."""
    diag_module = _StubModule.__new__(_StubModule)
    diag_module.ui_config = _StubUiConfig([_StubUiCfg("relation", identity_scope="diagram", id_prefix=None)])
    errors = validate_workspace_entity_ids(
        {"relation": [{"id": "bad-id", "label": "R"}]},
        diag_module,
    )
    assert errors == []


# ---------------------------------------------------------------------------
# E335 registration in generic registry
# ---------------------------------------------------------------------------


def test_e335_registered_in_generic_registry():
    """WorkspaceIdUniquenessContribution is present in the central generic registry."""
    from src.domain.diagrams.diagram_verification import get_generic_repository_contributions
    generic = get_generic_repository_contributions()
    assert any(isinstance(c, WorkspaceIdUniquenessContribution) for c in generic)
