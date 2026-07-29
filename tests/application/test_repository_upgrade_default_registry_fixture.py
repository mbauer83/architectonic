"""WU-G3a acceptance: `arch-repair upgrade`'s default registry, run against one fixture
repo carrying every format-drift pattern this plan introduced, reports every applicable
finding — not just the pre-existing multiplicity-rename/unrecognized-structure steps, but
all five new read-only detectors this WU adds."""

from __future__ import annotations

from pathlib import Path

from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.registry import DEFAULT_REGISTRY
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView


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
    }
    assert report.has_errors is False
    assert all(r.outcome == "skipped" for r in report.results)
