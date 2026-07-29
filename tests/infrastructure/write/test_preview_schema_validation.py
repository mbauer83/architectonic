"""Dry-run previews must validate Properties against the effective attribute schema.

A proposed entity is verified by writing it to a temp file that lives *outside* every
repo root, so the verifier cannot derive the governing repo from the file's location.
Unless the caller passes ``schema_repo_root``, the frontmatter- and attribute-schema
checks resolve no schemata and are silently skipped — meaning a dry_run would under-report
relative to the real write. These tests pin the fix: the preview honours the caller-supplied
governing repo and surfaces the same W042 the real write would.

Regression scenario: a ``service``-specialized application-component whose ``Lifecycle
State`` violates the shipped enum. Before the fix the dry_run reported no issues.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.entity import create_entity
from src.infrastructure.write.artifact_write.verify import verify_content_in_temp_path

_SERVICE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "attributes.application-component.service.schema.json",
    "type": "object",
    "required": [],
    "properties": {
        "Lifecycle State": {"type": "string", "enum": ["Planned", "Active", "Retired"]},
    },
    "additionalProperties": True,
}


def _eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-PREVIEW" / "architecture-repository"
    schemata = root / ".arch-repo" / "schemata"
    schemata.mkdir(parents=True)
    (schemata / _SERVICE_SCHEMA["$id"]).write_text(json.dumps(_SERVICE_SCHEMA), encoding="utf-8")
    return root


def _build_verifier(repo_root: Path) -> ArtifactVerifier:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


def _service_component_md(lifecycle_state: str) -> str:
    return f"""\
---
artifact-id: APP@1000000001.PreviW1.preview-service
artifact-type: application-component
name: "Preview Service"
version: 0.1.0
status: draft
specialization: service
last-updated: '2026-01-01'
---

<!-- §content -->

## Preview Service

A deployable service under test.

## Properties

| Attribute | Value |
|---|---|
| Lifecycle State | {lifecycle_state} |

<!-- §display -->

### archimate

```yaml
label: "Preview Service"
alias: APP_PreviW1
```
"""


class TestPreviewHonoursSchemaRepoRoot:
    """``verify_content_in_temp_path`` must resolve schemata from the governing repo."""

    def test_bad_enum_surfaces_w042_when_schema_repo_root_supplied(self, tmp_path: Path) -> None:
        repo_root = _eng_root(tmp_path)
        verifier = _build_verifier(repo_root)
        res = verify_content_in_temp_path(
            verifier=verifier,
            file_type="entity",
            desired_name="APP@1000000001.PreviW1.preview-service.md",
            content=_service_component_md("Nonexistent Stage"),
            schema_repo_root=repo_root,
        )
        assert "W042" in [i.code for i in res.issues]

    def test_no_schema_repo_root_skips_attribute_validation(self, tmp_path: Path) -> None:
        # Documents the temp-path-outside-repo behaviour: without the governing root the
        # verifier cannot locate the schemata, so the enum violation goes unreported. This
        # is exactly why the four entity dry-run call sites now pass schema_repo_root.
        repo_root = _eng_root(tmp_path)
        verifier = _build_verifier(repo_root)
        res = verify_content_in_temp_path(
            verifier=verifier,
            file_type="entity",
            desired_name="APP@1000000001.PreviW1.preview-service.md",
            content=_service_component_md("Nonexistent Stage"),
        )
        assert "W042" not in [i.code for i in res.issues]

    def test_valid_enum_emits_no_w042(self, tmp_path: Path) -> None:
        repo_root = _eng_root(tmp_path)
        verifier = _build_verifier(repo_root)
        res = verify_content_in_temp_path(
            verifier=verifier,
            file_type="entity",
            desired_name="APP@1000000001.PreviW1.preview-service.md",
            content=_service_component_md("Active"),
            schema_repo_root=repo_root,
        )
        assert "W042" not in [i.code for i in res.issues]


class TestCreateEntityDryRunValidatesAttributes:
    """End-to-end regression through the create_entity dry-run write path."""

    def test_dry_run_preview_reports_bad_enum(self, tmp_path: Path) -> None:
        repo_root = _eng_root(tmp_path)
        verifier = _build_verifier(repo_root)
        result = create_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_type="application-component",
            name="Fresh Service",
            summary="A service.",
            properties={"Lifecycle State": "Nonexistent Stage"},
            notes=None,
            specialization="service",
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        codes = [i["code"] for i in result.verification["issues"]]
        assert "W042" in codes

    def test_dry_run_preview_clean_for_valid_enum(self, tmp_path: Path) -> None:
        repo_root = _eng_root(tmp_path)
        verifier = _build_verifier(repo_root)
        result = create_entity(
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_type="application-component",
            name="Fresh Service",
            summary="A service.",
            properties={"Lifecycle State": "Active"},
            notes=None,
            specialization="service",
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        codes = [i["code"] for i in result.verification["issues"]]
        assert "W042" not in codes
