"""The checkout adapter observes a real repository and judges a tag against the installed signers file."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.application.software_update.version import ReleaseVersion
from src.infrastructure.software_update.checkout import RELEASE_SIGNERS, GitCheckout


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    identity = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "HOME": str(repo.parent), "PATH": "/usr/bin:/bin",
    }
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env={**identity, **(env or {})},
    )
    return result.stdout.strip()


@pytest.fixture()
def installation(tmp_path: Path) -> tuple[Path, Path]:
    """An 'origin' with a release tag, and a checkout cloned from it — the shape a user's install has."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.10.0"\n', encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "0.10.0")
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", "-q", str(origin), str(checkout))
    (origin / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.10.1"\n', encoding="utf-8")
    _git(origin, "commit", "-q", "-am", "0.10.1")
    _git(origin, "tag", "-a", "v0.10.1", "-m", "Release 0.10.1")
    return origin, checkout


def test_observation_reads_the_declared_version_commit_branch_and_cleanliness(installation: tuple[Path, Path]) -> None:
    _origin, checkout = installation
    software = GitCheckout(checkout).observe()

    assert software.version == ReleaseVersion(0, 10, 0)
    assert software.branch == "main" and software.clean and not software.signers_file_present
    assert software.commit == _git(checkout, "rev-parse", "HEAD")

    (checkout / "pyproject.toml").write_text("changed", encoding="utf-8")
    (checkout / "untracked.txt").write_text("x", encoding="utf-8")
    (checkout / ".arch").mkdir()
    (checkout / ".arch" / "state").write_text("x", encoding="utf-8")
    dirty = GitCheckout(checkout).observe()
    assert dirty.modified_tracked == ("pyproject.toml",)


def test_fetching_the_release_tag_returns_the_commit_it_names(installation: tuple[Path, Path]) -> None:
    origin, checkout = installation
    assert GitCheckout(checkout).fetch_tag("v0.10.1") == _git(origin, "rev-parse", "v0.10.1^{commit}")
    assert GitCheckout(checkout).fetch_tag("v9.9.9") is None


def test_an_unsigned_tag_is_not_enforced_without_a_signers_file_and_unsigned_with_one(
    installation: tuple[Path, Path],
) -> None:
    _origin, checkout = installation
    GitCheckout(checkout).fetch_tag("v0.10.1")
    assert GitCheckout(checkout).verify_tag("v0.10.1") == "not_enforced"

    (checkout / RELEASE_SIGNERS).parent.mkdir(parents=True)
    (checkout / RELEASE_SIGNERS).write_text('t@example.invalid namespaces="git" ssh-ed25519 AAAA\n', encoding="utf-8")
    assert GitCheckout(checkout).verify_tag("v0.10.1") == "unsigned"


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is needed to sign a tag")
def test_a_tag_signed_by_a_listed_key_verifies_and_one_by_another_key_is_untrusted(
    installation: tuple[Path, Path], tmp_path: Path,
) -> None:
    origin, checkout = installation
    keys = tmp_path / "keys"
    keys.mkdir()
    for name in ("release", "stranger"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(keys / name)], check=True)
    signers = checkout / RELEASE_SIGNERS
    signers.parent.mkdir(parents=True)
    release_key = (keys / "release.pub").read_text().strip()
    signers.write_text(f't@example.invalid namespaces="git" {release_key}\n', encoding="utf-8")

    def sign(tag: str, key: str) -> None:
        _git(origin, "-c", "gpg.format=ssh", "-c", f"user.signingkey={keys / key}", "tag", "-s", tag, "-m", tag)

    sign("v0.10.2", "release.pub")
    sign("v0.10.3", "stranger.pub")
    adapter = GitCheckout(checkout)
    adapter.fetch_tag("v0.10.2")
    adapter.fetch_tag("v0.10.3")

    assert adapter.verify_tag("v0.10.2") == "verified"
    assert adapter.verify_tag("v0.10.3") == "untrusted"
