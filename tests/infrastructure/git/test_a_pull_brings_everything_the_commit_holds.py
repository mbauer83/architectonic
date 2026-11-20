"""An engagement pull must leave the working tree at the commit the branch now names.

The pull publishes through an M4 transaction: the files the fetched commit changed are installed, and
the branch ref is moved to it. Which files is decided by one pathspec list in `git_sync_m4`
(`model/`, `docs/`, `diagram-catalog/`), while the ref moves for the whole commit. A repository laid
out by group keeps its entities under `projects/<slug>/model/`, and scratchpads live under
`scratchpads/` in every layout — neither is in the list. For those paths the working tree stays at
the old content under a branch that says the new commit, which git reads as a local edit undoing the
teammate's change; the next Save stages the whole tree and commits exactly that.

Driven on a real pair of clones against a bare repository, through the product's own pull
(`GitSyncManager._sync_engagement`), save (`commit_engagement_work`) and push (`push_engagement`),
because every one of the three is correct on its own and the loss only exists across them.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.infrastructure.git.git_sync import GitSyncManager, RepoSpec
from src.infrastructure.git.git_work_commits import commit_engagement_work, push_engagement
from src.infrastructure.rest.routers.sync.changes import list_changes
from src.infrastructure.workspace.mutation_gate import _reset_for_test
from tests.support.git_workflow_fixtures import git as _git
from tests.support.git_workflow_fixtures import valid_entity_md

LEGACY_ENTITY = "model/motivation/requirement/REQ@1000000911.PullLg.kept-under-model.md"
GROUPED_ENTITY = "projects/p/model/motivation/requirement/REQ@1000000912.PullGr.kept-under-projects.md"
SCRATCHPAD = "scratchpads/p/SCR@1000000913.PullSc.shared-thinking.scratchpad.yaml"
UNRELATED = "model/motivation/requirement/REQ@1000000914.PullUn.our-own-unrelated-work.md"
REVISED = "Revised By A Teammate"
ADDED_BY_THEM = "projects/p/model/motivation/requirement/REQ@1000000915.PullNw.added-by-a-teammate.md"


def _entity(rel: str, name: str) -> str:
    """An entity the save's own verification accepts, told apart across revisions by its name."""
    return valid_entity_md(Path(rel).name.removesuffix(".md"), name)


def _scratchpad(name: str) -> str:
    return (
        "artifact-id: SCR@1000000913.PullSc.shared-thinking\n"
        "artifact-type: scratchpad\n"
        f"name: {name}\n"
        "description: a pad two people share\n"
        "version: 0.1.0\n"
        "status: active\n"
        "meta-ontology: archimate-4\n"
    )


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clone(remote: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", "--quiet", str(remote), str(dest)], check=True, capture_output=True)
    _git(dest, "config", "user.email", "test@example.invalid")
    _git(dest, "config", "user.name", "Test")
    return dest


@dataclass
class Pair:
    remote: Path
    ours: Path
    theirs: Path

    def at_remote_tip(self, rel: str) -> str:
        return _git(self.remote, "show", f"main:{rel}")


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    """A bare remote and two clones of it, each a repository holding both layouts and a scratchpad."""
    _reset_for_test()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", "--quiet", str(remote)], check=True)
    seed = _clone(remote, tmp_path / "seed")
    _git(seed, "checkout", "-q", "-b", "main")
    _write(seed, LEGACY_ENTITY, _entity(LEGACY_ENTITY, "As First Written"))
    _write(seed, GROUPED_ENTITY, _entity(GROUPED_ENTITY, "As First Written"))
    _write(seed, SCRATCHPAD, _scratchpad("As first written"))
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "-u", "origin", "main")
    return Pair(remote, _clone(remote, tmp_path / "ours"), _clone(remote, tmp_path / "theirs"))


def _a_teammate_publishes(pair: Pair) -> None:
    """The teammate changes one entity in each layout and the scratchpad, saves, and pushes."""
    _write(pair.theirs, LEGACY_ENTITY, _entity(LEGACY_ENTITY, REVISED))
    _write(pair.theirs, GROUPED_ENTITY, _entity(GROUPED_ENTITY, REVISED))
    _write(pair.theirs, SCRATCHPAD, _scratchpad(REVISED))
    _write(pair.theirs, ADDED_BY_THEM, _entity(ADDED_BY_THEM, "Added By A Teammate"))
    commit_engagement_work(pair.theirs, "revise the requirement and the pad")
    push_engagement(pair.theirs)


def _we_pull(pair: Pair) -> None:
    manager = GitSyncManager([RepoSpec(pair.ours, "engagement")])
    asyncio.run(manager._sync_engagement(pair.ours))
    assert _git(pair.ours, "rev-parse", "HEAD") == _git(pair.remote, "rev-parse", "main"), (
        "the pull did not happen at all, so nothing below is about it"
    )


def test_a_pull_installs_what_the_commit_changed_under_model(pair: Pair) -> None:
    """The control: the flat layout's own directory is in the list, and arrives."""
    _a_teammate_publishes(pair)

    _we_pull(pair)

    assert REVISED in (pair.ours / LEGACY_ENTITY).read_text(encoding="utf-8")


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "git_sync_m4._MODEL_DIRS is [model, docs, diagram-catalog]: the pull moves the branch to the "
        "fetched commit but installs nothing under projects/ or scratchpads/, so those files keep "
        "their old content under a HEAD that says otherwise"
    ),
)
def test_a_pull_installs_what_the_commit_changed_under_projects_and_scratchpads(pair: Pair) -> None:
    _a_teammate_publishes(pair)

    _we_pull(pair)

    assert REVISED in (pair.ours / GROUPED_ENTITY).read_text(encoding="utf-8")
    assert REVISED in (pair.ours / SCRATCHPAD).read_text(encoding="utf-8")
    assert (pair.ours / ADDED_BY_THEM).exists()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "what the pull did not install reads as our own edit: git status reports both files modified "
        "straight after a pull into a clean clone, and the save dialog lists the entity as ours"
    ),
)
def test_a_pull_into_a_clean_clone_leaves_it_clean(pair: Pair) -> None:
    _a_teammate_publishes(pair)

    _we_pull(pair)

    # Tracked files only: what the transaction leaves under `.arch-repo/` is its own bookkeeping.
    assert _git(pair.ours, "status", "--porcelain", "--untracked-files=no") == ""
    assert list_changes(pair.ours) == []


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "the save after a pull stages the whole tree (STAGE_ALL_BUT_RUNTIME_STATE), so it commits the "
        "stale projects/ and scratchpads/ content as a change and the push publishes the reversal of "
        "the teammate's work — with no conflict, no refusal and no mention of either file"
    ),
)
def test_the_save_after_a_pull_does_not_undo_the_teammates_work(pair: Pair) -> None:
    _a_teammate_publishes(pair)
    _we_pull(pair)

    _write(pair.ours, UNRELATED, _entity(UNRELATED, "Our Own Unrelated Work"))
    commit_engagement_work(pair.ours, "add an unrelated requirement")
    push_engagement(pair.ours)

    published = _git(pair.remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert UNRELATED in published, "our own work did not reach the remote, so this shows nothing"
    assert REVISED in pair.at_remote_tip(LEGACY_ENTITY), "the control: model/ survives the round trip"
    undone = [rel for rel in (GROUPED_ENTITY, SCRATCHPAD) if REVISED not in pair.at_remote_tip(rel)]
    deleted = [rel for rel in (ADDED_BY_THEM,) if rel not in published]
    assert (undone, deleted) == ([], [])
