"""Before an update, the operator learns which enterprise tier stays at the older format, and an
administering deployment upgrades it.

An enterprise repository created by the deployment's own `arch-init` never received the shipped
`stress-analysis` document type: the migration evaluated it, printed "left unapplied" to stderr, and
the rehearsal line counted only "1 repositories". The report now carries the tiers it left alone, the
rehearsal names them, and a deployment whose backend serves with `--admin-mode` — the upgrade guide's
definition of owning that tier — has the updater pass `--admin-mode` to the migration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.software_update.installation import BackendObservation
from src.infrastructure.cli.arch_repair_upgrade import main_upgrade
from src.infrastructure.software_update.observation import deployment_identity_arguments, serves_in_admin_mode
from src.infrastructure.software_update.rehearsal import verdict_from_report
from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults


def _repository(root: Path) -> Path:
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)
    return root


def test_a_tier_left_alone_reaches_the_report_and_the_rehearsal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    engagement = _repository(tmp_path / "engagement")
    enterprise = _repository(tmp_path / "enterprise")
    (enterprise / ".arch-repo" / "documents" / "stress-analysis.json").unlink()

    assert main_upgrade(["--repo-root", str(engagement), "--enterprise-root", str(enterprise), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["tiers_left_alone"] == [{"root": str(enterprise.resolve()), "pending": 1}]
    verdict = verdict_from_report(report)
    assert verdict.left_alone == (f"{enterprise.resolve()}: 1 finding(s)",)


def test_an_administered_tier_is_upgraded_with_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    engagement = _repository(tmp_path / "engagement")
    enterprise = _repository(tmp_path / "enterprise")
    (enterprise / ".arch-repo" / "documents" / "stress-analysis.json").unlink()

    assert main_upgrade([
        "--repo-root", str(engagement), "--enterprise-root", str(enterprise), "--admin-mode", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["tiers_left_alone"] == []


def test_the_updater_passes_admin_mode_for_a_backend_that_serves_with_it() -> None:
    admin = BackendObservation(True, 1, 8000, True, ("--admin-mode",))
    plain = BackendObservation(True, 1, 8000, True, ())

    assert serves_in_admin_mode(admin) and not serves_in_admin_mode(plain)
    assert "--admin-mode" in deployment_identity_arguments(Path("/w"), admin_mode=True)
    assert "--admin-mode" not in deployment_identity_arguments(Path("/w"))
