"""A shipped default is written in the same bytes whether a repository is created or upgraded.

The workspace template and the upgrade's two ensure steps each spelled "write each shipped file that
is missing" and its byte format; they now ask `shipped_defaults`. Held as a pair: an empty repository
brought up by the template, and one brought up by the upgrade steps, hold the same files byte for byte
over what both ensure — the base document types and the attribute and frontmatter schemata.

The scopes differ by caller and that is recorded here, not hidden: creation also writes the assurance
document types; the upgrade, like the template's repair path, does not.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.steps.default_document_types_ensure import DefaultDocumentTypesEnsureStep
from src.application.repository_upgrade.steps.default_schemata_ensure import DefaultSchemataEnsureStep
from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS
from src.domain.repository.shipped_defaults import (
    DOCUMENT_TYPES_LOCATION,
    SCHEMATA_LOCATION,
    ensure_shipped,
    shipped_document_types,
    shipped_schemata,
)
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter
from src.infrastructure.workspace._assurance_doc_types import ASSURANCE_DOCUMENT_SCHEMAS
from src.infrastructure.workspace.engagement_repo_template import (
    DEFAULT_DOCUMENT_SCHEMAS,
    ensure_arch_repo_defaults,
)


def _files(root: Path, location: str) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted((root / location).glob("*.json"))}


def _upgraded(root: Path) -> Path:
    view, writer = FilesystemRepoUpgradeView(root), FilesystemRepoUpgradeWriter(root)
    for step in (DefaultDocumentTypesEnsureStep(), DefaultSchemataEnsureStep()):
        step.apply(view, writer, step.detect(view))
    return root


def test_repair_and_upgrade_write_the_same_bytes(tmp_path: Path) -> None:
    repaired = tmp_path / "repaired"
    repaired.mkdir()
    ensure_arch_repo_defaults(repaired)
    upgraded = _upgraded(tmp_path / "upgraded")

    for location in (DOCUMENT_TYPES_LOCATION, SCHEMATA_LOCATION):
        assert _files(repaired, location) == _files(upgraded, location), location
    assert set(_files(upgraded, DOCUMENT_TYPES_LOCATION)) == {f"{name}.json" for name in BASE_DOCUMENT_SCHEMAS}


def test_creation_adds_the_assurance_document_types_and_the_upgrade_does_not(tmp_path: Path) -> None:
    created = tmp_path / "created"
    created.mkdir()
    ensure_arch_repo_defaults(created, document_schemas=DEFAULT_DOCUMENT_SCHEMAS)
    upgraded = _upgraded(tmp_path / "upgraded")

    only_at_creation = set(_files(created, DOCUMENT_TYPES_LOCATION)) - set(_files(upgraded, DOCUMENT_TYPES_LOCATION))
    assert only_at_creation == {f"{name}.json" for name in ASSURANCE_DOCUMENT_SCHEMAS} - {
        f"{name}.json" for name in BASE_DOCUMENT_SCHEMAS
    }


def test_ensuring_writes_only_what_is_missing_and_answers_it() -> None:
    held = {one.location: "operator's own" for one in shipped_schemata()[:1]}
    written: dict[str, str] = {}
    shipped = (*shipped_schemata(), *shipped_document_types(BASE_DOCUMENT_SCHEMAS))

    added = ensure_shipped(shipped, present=lambda location: location in held, write=written.__setitem__)

    assert {one.location for one in added} == set(written) == {one.location for one in shipped} - set(held)
    assert all(written[one.location] == one.text and one.text.endswith("}\n") for one in added)
