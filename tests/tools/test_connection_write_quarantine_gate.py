"""WU-W2: the write-boundary quarantine gate on the connection side, exercised through the
real ``add_connection`` / ``edit_connection`` — the single choke point both the REST and MCP
transports funnel through. A conflicting attachment makes the
``archimate-serving/critical-serving`` pair quarantined; adding or re-pointing a connection
onto it must be rejected with the typed ``ProfileQuarantineError``, while a clean pair
writes normally. The entity mirror of this lives in ``test_entity_write_quarantine_gate.py``.
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
from src.infrastructure.write.artifact_write.connection import add_connection
from src.infrastructure.write.artifact_write.entity import create_entity

_CONNECTION_TYPE = "archimate-serving"
_SPECIALIZATION = "critical-serving"
_BASE_SCHEMA = f"connection-metadata.{_CONNECTION_TYPE}.schema.json"
_ATTACHMENT = f"connection-metadata.{_CONNECTION_TYPE}.{_SPECIALIZATION}.schema.json"
_SCORE_STRING = {"properties": {"Score": {"type": "string"}}}
_SCORE_NUMBER = {"properties": {"Score": {"type": "number"}}}

_SPECIALIZATIONS_YAML = f"""\
specializations:
  connection:
    {_CONNECTION_TYPE}:
      - slug: {_SPECIALIZATION}
        name: Critical Serving
"""


def _eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-W" / "architecture-repository"
    root.mkdir(parents=True)
    (root / ".arch-repo").mkdir()
    (root / ".arch-repo" / "specializations.yaml").write_text(_SPECIALIZATIONS_YAML, encoding="utf-8")
    return root


def _write_schema(repo_root: Path, filename: str, schema: dict) -> None:
    schemata = repo_root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True, exist_ok=True)
    (schemata / filename).write_text(json.dumps(schema), encoding="utf-8")


def _registry(repo_root: Path) -> ArtifactRegistry:
    index = shared_artifact_index([repo_root])
    index.refresh()
    return ArtifactRegistry(index)


def _verifier(registry: ArtifactRegistry) -> ArtifactVerifier:
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


def _two_entities(root: Path) -> tuple[str, str]:
    ids = []
    for name in ("Flow Source", "Flow Target"):
        registry = _registry(root)
        result = create_entity(
            repo_root=root, verifier=_verifier(registry), clear_repo_caches=lambda p: None,
            artifact_type="application-component", name=name, summary=None, properties=None,
            notes=None, specialization=None, artifact_id=None, version="0.1.0", status="draft",
            last_updated=None, dry_run=False,
        )
        ids.append(result.artifact_id)
    return ids[0], ids[1]


def _add(root: Path, source: str, target: str, *, specialization: str | None) -> object:
    registry = _registry(root)
    return add_connection(
        repo_root=root, registry=registry, verifier=_verifier(registry),
        clear_repo_caches=lambda p: None, source_entity=source, connection_type=_CONNECTION_TYPE,
        target_entity=target, description=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=True, specialization=specialization,
    )


def test_add_onto_a_quarantined_pair_is_rejected(tmp_path: Path) -> None:
    root = _eng_root(tmp_path)
    source, target = _two_entities(root)
    # base Score:string vs the specialization attachment Score:number => a Class B conflict.
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    _write_schema(root, _ATTACHMENT, _SCORE_NUMBER)
    clear_schema_cache()
    with pytest.raises(ProfileQuarantineError) as excinfo:
        _add(root, source, target, specialization=_SPECIALIZATION)
    assert "Score" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # REST → 400, MCP → tool error


def test_add_without_the_quarantined_specialization_is_allowed(tmp_path: Path) -> None:
    # Quarantine is per (connection-type, specialization): the unspecialized pair is fine.
    root = _eng_root(tmp_path)
    source, target = _two_entities(root)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    _write_schema(root, _ATTACHMENT, _SCORE_NUMBER)
    clear_schema_cache()
    result = _add(root, source, target, specialization=None)
    assert getattr(result, "artifact_id", None) is not None


def test_add_onto_a_clean_specialized_pair_is_allowed(tmp_path: Path) -> None:
    root = _eng_root(tmp_path)
    source, target = _two_entities(root)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    _write_schema(root, _ATTACHMENT, _SCORE_STRING)  # agrees with the base
    clear_schema_cache()
    result = _add(root, source, target, specialization=_SPECIALIZATION)
    assert getattr(result, "artifact_id", None) is not None


def test_edit_onto_a_quarantined_pair_is_rejected(tmp_path: Path) -> None:
    # Write a clean connection, then introduce the conflict and re-point it onto the
    # specialization — the edit is gated on the effective specialization like an add.
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection

    root = _eng_root(tmp_path)
    source, target = _two_entities(root)
    _write_schema(root, _BASE_SCHEMA, _SCORE_STRING)
    clear_schema_cache()
    registry = _registry(root)
    add_connection(
        repo_root=root, registry=registry, verifier=_verifier(registry),
        clear_repo_caches=lambda p: None, source_entity=source, connection_type=_CONNECTION_TYPE,
        target_entity=target, description=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=False,
    )
    _write_schema(root, _ATTACHMENT, _SCORE_NUMBER)
    clear_schema_cache()
    registry = _registry(root)
    with pytest.raises(ProfileQuarantineError):
        edit_connection(
            repo_root=root, registry=registry, verifier=_verifier(registry),
            clear_repo_caches=lambda p: None, source_entity=source, target_entity=target,
            connection_type=_CONNECTION_TYPE, specialization=_SPECIALIZATION, dry_run=True,
        )
