"""Tests for the `connection-metadata.{connection-type}.schema.json` convention: a
per-connection-type schema (opt-in, like `attributes.{artifact-type}.schema.json`) that
validates a connection's per-connection metadata block (the fenced YAML block under a
`### ` heading in an `.outgoing.md` file — today just `specialization`, open to future
per-connection metadata)."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifacts.schema import clear_schema_cache
from src.application.verification._verifier_rules_schema import check_connection_metadata_schema
from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo

_FAKE_PATH = Path("/tmp/connection.md")


def _fresh_result() -> VerificationResult:
    return VerificationResult(path=_FAKE_PATH, file_type="connection")


def _write_schema(repo_root: Path, connection_type: str, schema: dict) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / f"connection-metadata.{connection_type}.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )


def setup_function() -> None:
    clear_schema_cache()


class TestConnectionMetadataSchema:
    def test_no_schema_file_skips_validation(self, tmp_path: Path) -> None:
        result = _fresh_result()
        check_connection_metadata_schema(
            {"specialization": "anything"}, "archimate-assignment", tmp_path, result, "test"
        )
        assert result.issues == []

    def test_metadata_conforming_to_schema_is_silent(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path,
            "archimate-assignment",
            {"type": "object", "properties": {"specialization": {"type": "string"}}, "additionalProperties": True},
        )
        result = _fresh_result()
        check_connection_metadata_schema(
            {"specialization": "responsibility-assignment"}, "archimate-assignment", tmp_path, result, "test"
        )
        assert result.issues == []

    def test_metadata_violating_schema_is_w043(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path,
            "archimate-assignment",
            {"type": "object", "properties": {"priority": {"type": "integer"}}},
        )
        result = _fresh_result()
        check_connection_metadata_schema(
            {"priority": "not-an-integer"}, "archimate-assignment", tmp_path, result, "test"
        )
        assert [i.code for i in result.issues] == ["W043"]

    def test_schema_is_scoped_to_its_own_connection_type(self, tmp_path: Path) -> None:
        _write_schema(
            tmp_path,
            "archimate-assignment",
            {"type": "object", "properties": {"priority": {"type": "integer"}}},
        )
        result = _fresh_result()
        check_connection_metadata_schema(
            {"priority": "not-an-integer"}, "archimate-serving", tmp_path, result, "test"
        )
        assert result.issues == []


class TestEffectiveSchemaMerge:
    """WU-W2: the check validates against the EFFECTIVE schema for the connection's
    (type, specialization) pair — the connection mirror of E043's entity path."""

    def _catalog(self, attributes: dict) -> SpecializationCatalog:
        return SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="deployment-flow", name="Deployment Flow", concept_kind="connection",
                    parent_type="archimate-flow", module_alias="archimate-4", attributes=attributes,
                ),
            )
        )

    def test_specialization_contribution_is_validated(self, tmp_path: Path) -> None:
        result = _fresh_result()
        check_connection_metadata_schema(
            {"specialization": "deployment-flow", "priority": "not-an-integer"},
            "archimate-flow", tmp_path, result, "test",
            specialization_catalog=self._catalog({"priority": {"type": "integer"}}),
        )
        assert [i.code for i in result.issues] == ["W043"]

    def test_conflicting_merge_is_a_blocking_e045(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "archimate-flow", {"properties": {"scope": {"type": "string"}}})
        result = _fresh_result()
        check_connection_metadata_schema(
            {"specialization": "deployment-flow"}, "archimate-flow", tmp_path, result, "test",
            specialization_catalog=self._catalog({"scope": {"type": "integer"}}),
        )
        codes = [i.code for i in result.issues]
        assert "E045" in codes
        assert any(i.severity is Severity.ERROR and "scope" in i.message for i in result.issues)

    def test_an_unspecialized_connection_sees_only_the_base_schema(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "archimate-flow", {"properties": {"scope": {"type": "string"}}})
        result = _fresh_result()
        check_connection_metadata_schema(
            {}, "archimate-flow", tmp_path, result, "test",
            specialization_catalog=self._catalog({"scope": {"type": "integer"}}),
        )
        assert result.issues == []
