"""Repair primitive: bring an existing repo's .arch-repo to current defaults.

Covers the scenario behind the malformed personal enterprise repo — legacy schema files written
flat under .arch-repo/ with an empty schemata/ and no documents/ — plus idempotency and the
no-overwrite guarantee that protects an operator's local edits.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.infrastructure.workspace.engagement_repo_template import (
    BASE_DOCUMENT_SCHEMAS,
    DEFAULT_SCHEMATA,
    ensure_arch_repo_defaults,
)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "model").mkdir(parents=True)
    (repo / ".arch-repo").mkdir()
    return repo


def test_populates_missing_documents_schemata_and_config(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    summary = ensure_arch_repo_defaults(repo)

    docs = repo / ".arch-repo" / "documents"
    schem = repo / ".arch-repo" / "schemata"
    assert (docs / "standard.json").is_file()
    assert set(p.name for p in docs.glob("*.json")) == {f"{k}.json" for k in BASE_DOCUMENT_SCHEMAS}
    assert set(p.name for p in schem.glob("*.json")) == set(DEFAULT_SCHEMATA)
    assert (repo / ".arch-repo" / "config.yaml").is_file()
    assert "standard.json" in summary["documents"]
    assert summary["config"] == ["config.yaml"]


def test_new_repo_receives_assurance_attribute_schemas(tmp_path: Path) -> None:
    # Content migrated off the dormant OntologyModule.attribute_profiles surface (removed —
    # no live consumer had ever read it besides these very schemata-scaffolding defaults).
    repo = _make_repo(tmp_path)
    ensure_arch_repo_defaults(repo)

    schem = repo / ".arch-repo" / "schemata"
    for filename in (
        "attributes.hazard.schema.json",
        "attributes.risk.schema.json",
        "attributes.unsafe-control-action.schema.json",
        "attributes.assurance-constraint.schema.json",
        "attributes.control-structure-node.schema.json",
    ):
        assert (schem / filename).is_file(), f"Expected {filename} to be scaffolded into a new repo"
        schema = json.loads((schem / filename).read_text(encoding="utf-8"))
        assert schema["properties"], f"{filename} should declare at least one property"


def test_migrates_canonical_flat_files_and_drops_legacy_junk(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    arch = repo / ".arch-repo"
    # Legacy layout: a canonical schema written flat, plus the old mis-pluralised name.
    canonical = "attributes.requirement.schema.json"
    (arch / canonical).write_text('{"legacy": true}', encoding="utf-8")
    (arch / "frontmatter.entities.schema.json").write_text("{}", encoding="utf-8")

    summary = ensure_arch_repo_defaults(repo)

    # Flat files are gone; canonical content now lives under schemata/.
    assert not (arch / canonical).exists()
    assert not (arch / "frontmatter.entities.schema.json").exists()
    assert (arch / "schemata" / canonical).is_file()
    # The mis-pluralised junk is NOT resurrected under schemata/.
    assert not (arch / "schemata" / "frontmatter.entities.schema.json").exists()
    assert set(summary["migrated_flat"]) == {canonical, "frontmatter.entities.schema.json"}


def test_is_idempotent_and_never_overwrites(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    ensure_arch_repo_defaults(repo)
    # An operator edit to an existing schema must survive a second repair.
    edited = repo / ".arch-repo" / "schemata" / "attributes.driver.schema.json"
    edited.write_text('{"operator": "edit"}', encoding="utf-8")

    summary = ensure_arch_repo_defaults(repo)

    assert json.loads(edited.read_text()) == {"operator": "edit"}
    assert summary == {"documents": [], "schemata": [], "migrated_flat": [], "config": []}
