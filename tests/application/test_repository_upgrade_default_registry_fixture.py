"""`arch-repair upgrade`'s default registry against one fixture repository carrying every
format-drift pattern the product knows about: it reports each applicable finding, and applying
leaves the repository with nothing pending and the current contract stamped.

The fixture grows with the shipped surface. A release that adds a drift pattern and not a row
here would pass a registry test while leaving repositories in the field unrepaired, which is the
whole failure this file exists to prevent."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.registry import DEFAULT_REGISTRY, FORMAT_CONTRACT_VERSION
from src.infrastructure.repository_upgrade.config_store import read_format_contract_version
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_pre_plan_drift_fixture(root: Path) -> None:
    (root / ".arch-repo").mkdir(parents=True, exist_ok=True)

    # d9-multiplicity-rename: legacy include_cardinality key.
    _write(
        root,
        "diagram-catalog/diagrams/uncategorized/D1.md",
        "---\nartifact-id: DIA@1.abc.d1\nartifact-type: diagram\nname: D1\n"
        "connections:\n  - artifact_id: CONN@1.abc.c1\n    include_cardinality: true\n---\n@startuml\n@enduml\n",
    )

    # viewpoint-application-scan: malformed viewpoint: value (missing slug).
    _write(
        root,
        "diagram-catalog/diagrams/uncategorized/D2.md",
        "---\nartifact-id: DIA@1.abc.d2\nartifact-type: diagram\nname: D2\n"
        "viewpoint:\n  version: 1\n---\n@startuml\n@enduml\n",
    )

    # unrecognized-structure-scan: missing artifact-type.
    _write(root, "model/weird/WEIRD.md", "---\nartifact-id: WEIRD@1.abc.x\nname: X\n---\nbody\n")

    # connection-metadata-scan: malformed metadata fence, silently read as body text today.
    _write(
        root,
        "model/motivation/requirement/REQ@1.abc.name.outgoing.md",
        "---\nsource-entity: REQ@1.abc.name\nversion: 0.1.0\nstatus: active\nlast-updated: '2026-01-01'\n---\n"
        "### assignment → REQ@2.def.other\n\n```yaml\nspecialization: [unterminated\n```\n\nDescription.\n",
    )

    # specialization-declaration-scan: malformed specializations.yaml.
    _write(root, ".arch-repo/specializations.yaml", "specializations:\n  entity: [unterminated\n")

    # viewpoint-declaration-scan: malformed viewpoints.yaml.
    _write(root, ".arch-repo/viewpoints.yaml", "viewpoints:\n  - slug: [unterminated\n")

    # schema-file-scan: malformed JSON schema file.
    _write(root, ".arch-repo/schemata/attributes.requirement.schema.json", "{not valid json")

    # group-meta-ontology-archimate-4-rename: legacy 'archimate-next' meta_ontology value.
    _write(
        root,
        ".arch-repo/groups.yaml",
        "model-projects:\n- slug: p1\n  id: GRP@1.a.p1\n  name: P1\n  meta_ontology: archimate-next\n"
        "diagram-collections: []\ndocument-collections: []\n",
    )

    # d11-rendered-output-under-a-former-slug: a collection renamed by a version that moved the
    # sources and left the pictures, so the PNG download answers 404 for a diagram that is there.
    _write(
        root,
        "diagram-catalog/diagrams/current-name/ARC@1.abc.a-diagram.puml",
        "@startuml\n@enduml\n",
    )
    for suffix in (".png", ".svg"):
        _write(root, f"diagram-catalog/rendered/former-name/ARC@1.abc.a-diagram{suffix}", "binary-ish")


def test_default_registry_reports_every_applicable_finding(tmp_path: Path) -> None:
    _build_pre_plan_drift_fixture(tmp_path)
    view = FilesystemRepoUpgradeView(tmp_path)

    report = evaluate_repository(view, registry=DEFAULT_REGISTRY, software_version="0.0.0-test")

    assert set(report.unapplied_required_steps) == {
        "d9-multiplicity-rename",
        "viewpoint-application-scan",
        "unrecognized-structure-scan",
        "connection-metadata-scan",
        "specialization-declaration-scan",
        "viewpoint-declaration-scan",
        "schema-file-scan",
        "default-schemata-ensure",
        "group-meta-ontology-archimate-4-rename",
        # The outgoing-file fixture carries a date-only `last-updated`.
        "modification-stamp-datetime",
        "d11-rendered-output-under-a-former-slug",
    }
    assert report.has_errors is False
    assert all(r.outcome == "skipped" for r in report.results)


def test_applying_leaves_the_repository_with_nothing_pending(tmp_path: Path) -> None:
    """"Fully prepared" is the claim a release rests on, so it is asserted rather than assumed.

    Every finding this fixture carries that can be migrated mechanically is gone afterwards, the
    current contract version is stamped, and what remains is only what a person has to decide —
    each such finding naming what to do about it.
    """
    _build_pre_plan_drift_fixture(tmp_path)
    view = FilesystemRepoUpgradeView(tmp_path)
    writer = FilesystemRepoUpgradeWriter(tmp_path)

    apply_repository(view, writer, registry=DEFAULT_REGISTRY, software_version="0.0.0-test")
    after = evaluate_repository(view, registry=DEFAULT_REGISTRY, software_version="0.0.0-test")

    assert read_format_contract_version(tmp_path) == FORMAT_CONTRACT_VERSION
    remaining = [r.finding for r in after.results if r.finding.auto_migratable]
    assert remaining == [], [f.finding_id for f in remaining]
    for result in after.results:
        assert result.finding.manual_instructions, result.finding.finding_id


def test_the_rendered_output_is_where_the_download_looks_for_it(tmp_path: Path) -> None:
    """The release's own drift pattern, applied end to end through the default registry."""
    _build_pre_plan_drift_fixture(tmp_path)

    apply_repository(
        FilesystemRepoUpgradeView(tmp_path),
        FilesystemRepoUpgradeWriter(tmp_path),
        registry=DEFAULT_REGISTRY,
        software_version="0.0.0-test",
    )

    for suffix in (".png", ".svg"):
        assert (tmp_path / f"diagram-catalog/rendered/current-name/ARC@1.abc.a-diagram{suffix}").exists(), suffix
    assert not (tmp_path / "diagram-catalog/rendered/former-name").exists()
