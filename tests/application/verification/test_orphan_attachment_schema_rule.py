"""W044 — orphan specialization-attachment schema file, wired as a generic repository
verification contribution (same mechanism as the E335 workspace-id-uniqueness check)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.application.verification._orphan_attachment_schema_rule import OrphanAttachmentSchemaContribution
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.diagrams.diagram_verification import RepositoryVerificationContext
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo


@dataclass
class _StubCatalogs:
    specializations: SpecializationCatalog


def _write_schema(repo_root: Path, filename: str) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / filename).write_text(json.dumps({"properties": {}}), encoding="utf-8")


def _run(tmp_path: Path, catalog: SpecializationCatalog) -> VerificationResult:
    ctx = RepositoryVerificationContext(
        committed=None, candidate=None, location=str(tmp_path), catalogs=_StubCatalogs(specializations=catalog)
    )
    result = VerificationResult(path=tmp_path, file_type="diagram")
    OrphanAttachmentSchemaContribution().run(ctx, result)
    return result


class TestOrphanAttachmentSchemaContribution:
    def test_no_catalogs_is_silent(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.ghost.schema.json")
        ctx = RepositoryVerificationContext(committed=None, candidate=None, location=str(tmp_path), catalogs=None)
        result = VerificationResult(path=tmp_path, file_type="diagram")
        OrphanAttachmentSchemaContribution().run(ctx, result)
        assert result.issues == []

    def test_declared_specialization_attachment_is_silent(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.business-collaboration.schema.json")
        catalog = SpecializationCatalog(
            (
                SpecializationInfo(
                    slug="business-collaboration", name="Business Collaboration",
                    concept_kind="entity", parent_type="collaboration", module_alias="archimate-4",
                ),
            )
        )
        assert _run(tmp_path, catalog).issues == []

    def test_orphan_attachment_is_w044(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "attributes.collaboration.ghost-collaboration.schema.json")
        result = _run(tmp_path, SpecializationCatalog.empty())
        assert [i.code for i in result.issues] == ["W044"]
