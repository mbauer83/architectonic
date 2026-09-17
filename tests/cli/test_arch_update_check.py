"""`arch-update` without `--commit` reports and writes nothing, in the human form and as JSON."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.application.software_update.installation import (
    BackendObservation,
    DependencySelection,
    InstallationObservation,
    InstalledSoftware,
    StoreObservation,
    Tooling,
)
from src.application.software_update.release import PublishedRelease, ReleaseAsset, sha256_of
from src.application.software_update.version import ReleaseVersion
from src.infrastructure.cli import arch_update

BUNDLE = b"gui bundle bytes"
INSTALLED = InstalledSoftware(ReleaseVersion(0, 10, 0), "abc1234def", "main", (), True, "stamp", "1.2026.3")
RELEASE = PublishedRelease(
    ReleaseVersion(0, 10, 1), "v0.10.1", "def4567abc", "2026-10-02T09:00:00Z", False,
    (
        ReleaseAsset("architectonic-gui-0.10.1.tar.gz", "https://x/gui", sha256_of(BUNDLE), len(BUNDLE)),
        ReleaseAsset("SHA256SUMS", "https://x/sums", None, 90),
    ),
)


class FakeSource:
    def __init__(self, release: PublishedRelease | None, *, sums_digest: str | None = None) -> None:
        self.release = release
        self.sums_digest = sums_digest or sha256_of(BUNDLE)

    def latest(self, *, include_prerelease: bool) -> PublishedRelease | None:
        return self.release

    def by_version(self, version: ReleaseVersion) -> PublishedRelease | None:
        return self.release if self.release and self.release.version == version else None

    def download(self, asset: ReleaseAsset) -> bytes:
        if asset.name == "SHA256SUMS":
            return f"{self.sums_digest}  architectonic-gui-0.10.1.tar.gz\n".encode()
        return BUNDLE


class FakeCheckout:
    def __init__(self, installed: InstalledSoftware, *, fetched: str | None = RELEASE.commit) -> None:
        self.installed = installed
        self.fetched = fetched
        self.fetched_tags: list[str] = []

    def observe(self) -> InstalledSoftware:
        return self.installed

    def fetch_tag(self, tag: str) -> str | None:
        self.fetched_tags.append(tag)
        return self.fetched

    def verify_tag(self, tag: str) -> str:
        return "not_enforced"

    def on_main_branch(self) -> bool:
        return True


def _observation(software: InstalledSoftware) -> InstallationObservation:
    return InstallationObservation(
        kind="local-checkout", software=software, selection=DependencySelection(("gui",), ()),
        backend=BackendObservation(True, 4242, 8000, True, ()), store=StoreObservation(True, True, "manual", True),
        remotes_needing_credentials=(), tooling=Tooling(True, True, False, False), interactive=True,
    )


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    def wire(source: FakeSource, checkout: FakeCheckout) -> None:
        monkeypatch.setattr(arch_update, "GitHubReleases", lambda *a, **k: source)
        monkeypatch.setattr(arch_update, "GitCheckout", lambda root: checkout)
        monkeypatch.setattr(arch_update, "observe_installation", lambda root, software, **kw: _observation(software))
        monkeypatch.setattr(arch_update, "deployment_identity_arguments", lambda root: ("--workspace", str(root)))
        # The rehearsal is a real worktree and `uv sync`; every test that is not about it gets a clear verdict.
        monkeypatch.setattr(
            arch_update, "rehearse",
            lambda root, **kwargs: _clear_verdict(),
        )
    return wire


def test_the_dry_run_reports_an_available_verified_update_and_exits_zero(wired, capsys) -> None:  # noqa: ANN001
    checkout = FakeCheckout(INSTALLED)
    wired(FakeSource(RELEASE), checkout)

    assert arch_update.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["update_available"] is True
    assert report["installed"]["version"] == "0.10.0" and report["release"]["version"] == "0.10.1"
    assert report["verification"]["commit_matches"] is True
    assert report["verification"]["assets"][0]["verdict"] == "verified"
    assert checkout.fetched_tags == ["v0.10.1"]
    first_steps = [step["key"] for step in report["plan"]["steps"]][:3]
    assert first_steps == ["stop_backend", "move_checkout", "sync_environment"]
    assert report["plan"]["gui"] == "from_release"


def test_a_digest_mismatch_is_reported_as_such_and_still_exits_zero_on_a_dry_run(wired, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE, sums_digest="0" * 64), FakeCheckout(INSTALLED))

    assert arch_update.main([]) == 0
    out = capsys.readouterr().out
    assert "DIGEST MISMATCH" in out and "SHA256SUMS" in out
    assert "refused" in out and "nothing was installed" in out


def test_an_installation_at_the_newest_release_is_up_to_date_and_fetches_nothing(wired, capsys) -> None:  # noqa: ANN001
    checkout = FakeCheckout(replace(INSTALLED, version=ReleaseVersion(0, 10, 1)))
    wired(FakeSource(RELEASE), checkout)

    assert arch_update.main([]) == 0
    assert "up to date" in capsys.readouterr().out
    assert checkout.fetched_tags == []


def test_a_release_whose_tag_is_not_on_the_origin_says_the_commit_does_not_match(wired, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE), FakeCheckout(INSTALLED, fetched=None))

    assert arch_update.main([]) == 0
    assert "COMMIT DOES NOT MATCH" in capsys.readouterr().out


def test_a_requested_version_that_is_not_a_release_version_is_a_usage_error(capsys) -> None:  # noqa: ANN001
    assert arch_update.main(["--to", "latest"]) == 2
    assert "not a release version" in capsys.readouterr().err


def _clear_verdict() -> arch_update.RehearsalVerdict:
    return arch_update.RehearsalVerdict(2, 1, 3, (), (), ())


def test_the_dry_run_rehearses_the_release_and_reports_the_verdict(wired, monkeypatch, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE), FakeCheckout(INSTALLED))
    calls: list[dict] = []

    def fake_rehearse(root, **kwargs):  # noqa: ANN001, ANN202
        calls.append(kwargs)
        return _clear_verdict()

    monkeypatch.setattr(arch_update, "rehearse", fake_rehearse)

    assert arch_update.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert calls[0]["start_point"] == "v0.10.1" and calls[0]["upgrade_arguments"][0] == "--workspace"
    assert report["rehearsal"]["repositories"] == 2 and report["plan"] is not None


def test_a_rehearsal_with_a_blocking_finding_refuses_the_update(wired, monkeypatch, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE), FakeCheckout(INSTALLED))
    verdict = arch_update.RehearsalVerdict(2, 1, 0, ("enterprise: selection-divergent",), (), ())
    monkeypatch.setattr(arch_update, "rehearse", lambda root, **kwargs: verdict)

    assert arch_update.main([]) == 0
    out = capsys.readouterr().out
    assert "rehearsal   arch-repair upgrade 0.10.1" in out and "1 blocking" in out
    assert "refused" in out and "selection-divergent" in out


def test_a_rehearsal_that_cannot_run_refuses_and_names_the_escape_hatch(wired, monkeypatch, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE), FakeCheckout(INSTALLED))

    def failing(root, **kwargs):  # noqa: ANN001, ANN202
        raise arch_update.RehearsalFailed("syncing failed (1): no matching distribution")

    monkeypatch.setattr(arch_update, "rehearse", failing)

    assert arch_update.main([]) == 0
    out = capsys.readouterr().out
    assert "could not be run: syncing failed" in out and "--no-rehearse" in out


def test_no_rehearse_skips_the_worktree_and_still_plans(wired, monkeypatch, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE), FakeCheckout(INSTALLED))
    monkeypatch.setattr(arch_update, "rehearse", lambda *a, **k: pytest.fail("rehearsed despite --no-rehearse"))

    assert arch_update.main(["--no-rehearse", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rehearsal"] is None and report["plan"] is not None


@pytest.mark.verifies("REQ@1789640735.7Qke86l")
def test_an_update_refused_before_the_rehearsal_never_creates_a_worktree(wired, monkeypatch, capsys) -> None:  # noqa: ANN001
    wired(FakeSource(RELEASE, sums_digest="0" * 64), FakeCheckout(INSTALLED))
    monkeypatch.setattr(arch_update, "rehearse", lambda *a, **k: pytest.fail("rehearsed a refused update"))

    assert arch_update.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["rehearsal"] is None
