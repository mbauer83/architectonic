"""WU-Q3: the write-boundary quarantine gate, exercised through the real ``create_entity`` /
``edit_entity`` — the single choke point both the REST and MCP transports funnel through, so
covering it here covers every transport. A conflicting specialization attachment makes the
``application-component/service`` pair quarantined; a create or edit onto it must be rejected
with the typed ``ProfileQuarantineError`` (a ValueError → HTTP 400 / MCP error), while a
clean pair writes normally.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.artifact_schema import clear_schema_cache
from src.application.profile_quarantine import ProfileQuarantineError
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.entity import create_entity
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

_BASE_SCHEMA = "attributes.application-component.schema.json"
_SERVICE_ATTACHMENT = "attributes.application-component.service.schema.json"
_SCORE_STRING = {"properties": {"Score": {"type": "string"}}}
_SCORE_NUMBER = {"properties": {"Score": {"type": "number"}}}


def _eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-Q" / "architecture-repository"
    root.mkdir(parents=True)
    return root


def _write_schema(repo_root: Path, filename: str, schema: dict) -> None:
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / filename).write_text(json.dumps(schema), encoding="utf-8")


def _verifier(repo_root: Path) -> ArtifactVerifier:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


def _quarantine_fixture(tmp_path: Path) -> Path:
    # base Score:string vs the 'service' attachment Score:number => a Class B conflict.
    root = _eng_root(tmp_path)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    _write_schema(root, _SERVICE_ATTACHMENT, _SCORE_NUMBER)
    clear_schema_cache()
    return root


def _create(root: Path, *, specialization: str | None) -> object:
    return create_entity(
        repo_root=root, verifier=_verifier(root), clear_repo_caches=lambda p: None,
        artifact_type="application-component", name="Gate Probe", summary=None, properties=None,
        notes=None, specialization=specialization, artifact_id=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=True,
    )


def test_create_onto_a_quarantined_pair_is_rejected(tmp_path: Path) -> None:
    root = _quarantine_fixture(tmp_path)
    with pytest.raises(ProfileQuarantineError) as excinfo:
        _create(root, specialization="service")
    assert "Score" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # REST → 400, MCP → tool error


def test_create_onto_a_clean_pair_is_allowed(tmp_path: Path) -> None:
    # No conflicting attachment: the same type with no specialization writes normally.
    root = _eng_root(tmp_path)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    clear_schema_cache()
    result = _create(root, specialization=None)
    assert getattr(result, "artifact_id", None) is not None  # produced a result, no rejection


def test_edit_onto_a_quarantined_pair_is_rejected(tmp_path: Path) -> None:
    # Create a clean entity, then introduce the conflict and edit it — the edit is gated on
    # the effective (post-merge) specialization exactly like a create.
    root = _eng_root(tmp_path)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    clear_schema_cache()
    created = create_entity(
        repo_root=root, verifier=_verifier(root), clear_repo_caches=lambda p: None,
        artifact_type="application-component", name="Editable", summary=None, properties=None,
        notes=None, specialization="service", artifact_id=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=False,
    )
    _write_schema(root, _SERVICE_ATTACHMENT, _SCORE_NUMBER)
    clear_schema_cache()
    index = shared_artifact_index([root])
    index.refresh()
    registry = ArtifactRegistry(index)
    verifier = ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))
    with pytest.raises(ProfileQuarantineError):
        edit_entity(
            repo_root=root, registry=registry, verifier=verifier,
            clear_repo_caches=lambda p: None, artifact_id=created.artifact_id, summary="touch", dry_run=True,
        )
