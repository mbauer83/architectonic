"""An installation configured the way the guide says can be updated, and a diverged `main` is refused early.

The installation guide has the operator edit `arch-workspace.yaml` (repositories, port), and
`arch-assurance init` / `use-backend` write `config/settings.yaml`. Both are tracked, and `arch-update`
refused any checkout with a modified tracked file, advising "commit or stash them". Stashing removed the
configuration the update then ran against; committing diverged `main`, which the dry run still planned
as a fast-forward and the move phase then failed on. These tests drive a real git checkout through
the observation, the dry-run relation and the move.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.software_update.checkout import CheckoutError, GitCheckout

_WORKSPACE = "arch-workspace.yaml"
_SHIPPED = "engagement:\n  local: engagements/demo\n\nenterprise:\n  local: enterprise-repository\n"
_EDITED = "engagement:\n  local: /srv/ours\n\nenterprise:\n  local: enterprise-repository\n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.org", "-c", "user.name=t", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _pair(tmp_path: Path, *, release_workspace: str | None = None) -> tuple[Path, Path]:
    """An origin at 0.10.0 and a tagged 0.10.1 (optionally changing the workspace file); a clone at 0.10.0."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "pyproject.toml").write_text('[project]\nversion = "0.10.0"\n')
    (origin / _WORKSPACE).write_text(_SHIPPED)
    (origin / "config").mkdir()
    (origin / "config" / "settings.yaml").write_text("backend:\n  port: 8000\n")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "first")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (origin / "pyproject.toml").write_text('[project]\nversion = "0.10.1"\n')
    if release_workspace is not None:
        (origin / _WORKSPACE).write_text(release_workspace)
    _git(origin, "commit", "-qam", "second")
    _git(origin, "tag", "v0.10.1")
    return origin, clone


def test_edited_configuration_is_kept_apart_from_a_modified_checkout(tmp_path: Path) -> None:
    _, clone = _pair(tmp_path)
    (clone / _WORKSPACE).write_text(_EDITED)
    (clone / "config" / "settings.yaml").write_text("backend:\n  port: 8031\n")

    observed = GitCheckout(clone).observe()

    assert observed.clean and observed.modified_tracked == ()
    assert set(observed.local_configuration) == {_WORKSPACE, "config/settings.yaml"}


def test_a_flag_that_hides_configuration_edits_is_observed(tmp_path: Path) -> None:
    _, clone = _pair(tmp_path)
    (clone / _WORKSPACE).write_text(_EDITED)
    _git(clone, "update-index", "--skip-worktree", _WORKSPACE)

    assert GitCheckout(clone).observe().hidden_configuration == (_WORKSPACE,)


def test_a_release_that_leaves_the_file_alone_keeps_the_edit_through_move_and_restore(tmp_path: Path) -> None:
    _, clone = _pair(tmp_path)
    (clone / _WORKSPACE).write_text(_EDITED)
    checkout = GitCheckout(clone)
    before = checkout.observe()
    target = checkout.fetch_tag("v0.10.1")
    assert target is not None
    relation = checkout.relation_to(target, before.local_configuration)
    assert relation.fast_forwardable and relation.configuration_changed == ()

    carry = tmp_path / "carry"
    checkout.move_to("v0.10.1", "fast_forward", carry=carry)
    assert str(checkout.observe().version) == "0.10.1"
    assert (clone / _WORKSPACE).read_text() == _EDITED

    checkout.restore(before.commit, before.branch, carry=carry)
    assert checkout.observe().commit == before.commit
    assert (clone / _WORKSPACE).read_text() == _EDITED


def test_a_release_that_changes_the_file_gets_the_edit_merged_onto_its_version(tmp_path: Path) -> None:
    released = _SHIPPED + "\nbackend:\n  port: 8000\n"
    _, clone = _pair(tmp_path, release_workspace=released)
    (clone / _WORKSPACE).write_text(_EDITED)
    checkout = GitCheckout(clone)
    before = checkout.observe()
    target = checkout.fetch_tag("v0.10.1")
    assert target is not None
    relation = checkout.relation_to(target, before.local_configuration)
    assert relation.configuration_changed == (_WORKSPACE,) and relation.configuration_conflicts == ()

    carry = tmp_path / "carry"
    checkout.move_to("v0.10.1", "fast_forward", carry=carry)
    merged = (clone / _WORKSPACE).read_text()
    assert "/srv/ours" in merged and "port: 8000" in merged

    checkout.restore(before.commit, before.branch, carry=carry)
    assert checkout.observe().commit == before.commit
    assert (clone / _WORKSPACE).read_text() == _EDITED


def test_conflicting_edits_are_found_in_the_dry_run_and_refused_by_the_move(tmp_path: Path) -> None:
    released = _SHIPPED.replace("engagements/demo", "engagements/renamed-demo")
    _, clone = _pair(tmp_path, release_workspace=released)
    (clone / _WORKSPACE).write_text(_EDITED)
    checkout = GitCheckout(clone)
    target = checkout.fetch_tag("v0.10.1")
    assert target is not None

    relation = checkout.relation_to(target, checkout.observe().local_configuration)
    assert relation.configuration_conflicts == (_WORKSPACE,)

    with pytest.raises(CheckoutError, match="conflict"):
        checkout.move_to("v0.10.1", "fast_forward", carry=tmp_path / "carry")


def test_a_main_with_local_commits_is_seen_as_diverged(tmp_path: Path) -> None:
    _, clone = _pair(tmp_path)
    (clone / _WORKSPACE).write_text(_EDITED)
    _git(clone, "commit", "-qam", "local: our workspace")
    checkout = GitCheckout(clone)
    target = checkout.fetch_tag("v0.10.1")
    assert target is not None

    relation = checkout.relation_to(target, ())

    assert not relation.fast_forwardable and relation.local_commits == 1
    assert relation.merge_base == _git(clone, "rev-parse", "HEAD~1")


def test_the_remedy_s_two_commands_clear_either_flag(tmp_path: Path) -> None:
    # `git update-index --no-skip-worktree --no-assume-unchanged <file>` applies only the last option,
    # which left a skip-worktree flag in place; the remedy names one command per flag.
    _, clone = _pair(tmp_path)
    (clone / _WORKSPACE).write_text(_EDITED)
    _git(clone, "update-index", "--skip-worktree", _WORKSPACE)

    _git(clone, "update-index", "--no-skip-worktree", _WORKSPACE)
    _git(clone, "update-index", "--no-assume-unchanged", _WORKSPACE)

    observed = GitCheckout(clone).observe()
    assert observed.hidden_configuration == () and observed.local_configuration == (_WORKSPACE,)
