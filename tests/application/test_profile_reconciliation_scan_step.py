"""WU-R1: the reconciliation reporter flags attribute-profile conflicts (quarantined
pairs), is non-destructive (detect-only, never rewrites operator content), and stays quiet
on a clean repo."""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_schema import clear_schema_cache
from src.application.repository_upgrade.steps.profile_reconciliation_scan import ProfileReconciliationScanStep
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView

_PROFILES = """\
profile_schema: 1
profiles:
  metrics:
    version: 1
    attributes:
      Score: {type: number}
"""

_SPECIALIZATIONS = """\
specializations:
  entity:
    application-component:
      - slug: metric-service
        profiles: [metrics]
"""

_BASE_SCORE_STRING = '{"properties": {"Score": {"type": "string"}}}'


def _repo(tmp_path: Path, *, base_score_type: str, bind: bool) -> Path:
    root = tmp_path / "repo"
    arch = root / ".arch-repo"
    (arch / "schemata").mkdir(parents=True)
    (arch / "schemata" / "attributes.application-component.schema.json").write_text(
        f'{{"properties": {{"Score": {{"type": "{base_score_type}"}}}}}}', encoding="utf-8"
    )
    (arch / "profiles.yaml").write_text(_PROFILES, encoding="utf-8")
    if bind:
        (arch / "specializations.yaml").write_text(_SPECIALIZATIONS, encoding="utf-8")
    clear_schema_cache()
    return root


def test_conflicting_bound_profile_is_reported_as_quarantined(tmp_path: Path) -> None:
    root = _repo(tmp_path, base_score_type="string", bind=True)  # base string vs metrics number
    findings = ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root))
    assert len(findings) == 1
    finding = findings[0]
    # The concept kind is part of the finding identity — an entity and a connection may
    # each declare the same parent-type/slug pair.
    assert finding.finding_id.startswith("profile-conflict:entity:application-component/metric-service")
    assert finding.severity == "warning"
    assert finding.auto_migratable is False  # reconciliation is report-only in R1
    assert "Score" in finding.description


def test_finding_carries_the_three_proposed_resolutions(tmp_path: Path) -> None:
    # WU-R2: rename / align-type / unbind, named concretely and numbered, plus the
    # bound-profile name so the operator knows what to unbind.
    root = _repo(tmp_path, base_score_type="string", bind=True)
    finding = ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root))[0]
    instructions = finding.manual_instructions or ""
    assert "Resolve by one of: (1)" in instructions
    assert "Rename" in instructions
    assert "Align the type" in instructions
    assert "'metrics'" in instructions  # the bound profile is named in the unbind proposal
    assert "cannot be created or edited" in instructions  # the consequence still stated


def test_conflicts_are_never_auto_migrated(tmp_path: Path) -> None:
    # WU-R2's load-bearing guarantee: an ambiguous, operator-authored conflict is never
    # rewritten automatically — every finding is manual, with no rewrite_summary.
    root = _repo(tmp_path, base_score_type="string", bind=True)
    for finding in ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root)):
        assert finding.auto_migratable is False
        assert finding.rewrite_summary is None


def test_connection_specialization_conflicts_are_reported_too(tmp_path: Path) -> None:
    """WU-W2: a connection specialization binds profiles on the same terms as an entity
    one, so scanning only entities would report half the repo's conflicts."""
    root = tmp_path / "repo"
    arch = root / ".arch-repo"
    (arch / "schemata").mkdir(parents=True)
    (arch / "schemata" / "connection-metadata.archimate-flow.schema.json").write_text(
        _BASE_SCORE_STRING, encoding="utf-8"
    )
    (arch / "profiles.yaml").write_text(_PROFILES, encoding="utf-8")
    (arch / "specializations.yaml").write_text(
        "specializations:\n"
        "  connection:\n"
        "    archimate-flow:\n"
        "      - slug: metric-flow\n"
        "        profiles: [metrics]\n",
        encoding="utf-8",
    )
    clear_schema_cache()
    findings = ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root))
    assert len(findings) == 1
    assert findings[0].finding_id.startswith("profile-conflict:connection:archimate-flow/metric-flow")
    assert "Score" in findings[0].description
    assert "Connections" in findings[0].manual_instructions


def test_non_conflicting_binding_is_quiet(tmp_path: Path) -> None:
    root = _repo(tmp_path, base_score_type="number", bind=True)  # base number == metrics number
    assert ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root)) == []


def test_no_repo_specializations_is_quiet(tmp_path: Path) -> None:
    root = _repo(tmp_path, base_score_type="string", bind=False)
    assert ProfileReconciliationScanStep().detect(FilesystemRepoUpgradeView(root)) == []


def test_report_only_writes_nothing(tmp_path: Path) -> None:
    from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeWriter

    root = _repo(tmp_path, base_score_type="string", bind=True)
    view = FilesystemRepoUpgradeView(root)
    step = ProfileReconciliationScanStep()
    before = (root / ".arch-repo" / "specializations.yaml").read_text(encoding="utf-8")
    applied = step.apply(view, FilesystemRepoUpgradeWriter(root), step.detect(view))
    assert applied == []
    assert (root / ".arch-repo" / "specializations.yaml").read_text(encoding="utf-8") == before
