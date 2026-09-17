"""The checkout reaches a tag by fast-forward or detachment, and returns to where it was."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.software_update.checkout import CheckoutError, GitCheckout


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.org", "-c", "user.name=t", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """An origin with two commits and a tag on the second; a clone still at the first."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "pyproject.toml").write_text('[project]\nversion = "0.10.0"\n')
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "first")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (origin / "pyproject.toml").write_text('[project]\nversion = "0.10.1"\n')
    _git(origin, "commit", "-qam", "second")
    _git(origin, "tag", "v0.10.1")
    return origin, clone


def test_a_fast_forward_brings_the_branch_to_the_tag_and_restore_returns_it(pair: tuple[Path, Path]) -> None:
    _, clone = pair
    checkout = GitCheckout(clone)
    before = checkout.observe()
    target = checkout.fetch_tag("v0.10.1")

    checkout.move_to("v0.10.1", "fast_forward")
    after = checkout.observe()
    assert after.commit == target and after.branch == "main" and str(after.version) == "0.10.1"

    checkout.restore(before.commit, before.branch)
    restored = checkout.observe()
    assert restored.commit == before.commit and restored.branch == "main" and str(restored.version) == "0.10.0"


def test_a_detached_move_leaves_the_branch_where_it_was(pair: tuple[Path, Path]) -> None:
    _, clone = pair
    checkout = GitCheckout(clone)
    before = checkout.observe()
    checkout.fetch_tag("v0.10.1")

    checkout.move_to("v0.10.1", "detach")

    assert checkout.observe().branch is None
    assert _git(clone, "rev-parse", "main") == before.commit
    checkout.restore(before.commit, "main")
    assert checkout.observe().branch == "main"


def test_a_fast_forward_that_is_not_one_is_refused(pair: tuple[Path, Path]) -> None:
    _, clone = pair
    (clone / "local.txt").write_text("x")
    _git(clone, "add", ".")
    _git(clone, "commit", "-qm", "diverged")
    checkout = GitCheckout(clone)
    checkout.fetch_tag("v0.10.1")

    with pytest.raises(CheckoutError, match="moving the checkout"):
        checkout.move_to("v0.10.1", "fast_forward")
