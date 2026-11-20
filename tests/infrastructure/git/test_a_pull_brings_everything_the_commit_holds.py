"""A pull must leave the working tree at the commit the branch now names.

The pull publishes through an M4 transaction: the files the fetched commit changed are installed, and
the branch ref is moved to it. The ref moves for the whole commit, so the files have to as well. They
did not: the pull installed `model/`, `docs/` and `diagram-catalog/` only, and a repository laid out
by group keeps its entities under `projects/<slug>/model/`, its scratchpads under `scratchpads/` and
its configuration under `.arch-repo/`. Those stayed at their old content under a branch that said
the new commit, which git reads as a local edit undoing the teammate's change; the next save staged
the whole tree and published exactly that.

Driven on real clones against a bare repository, through the product's own pull — the engagement
fast-forward, the engagement rebase and the enterprise pull, which share one publisher — and its own
save (`commit_engagement_work`) and push (`push_engagement`), because each is correct alone and the
loss only existed across them.

The other half is what a pull must *not* do: replace a file holding work nobody has committed.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.infrastructure.git.git_repository_state import has_uncommitted_changes
from src.infrastructure.git.git_sync import GitSyncManager, RepoSpec
from src.infrastructure.git.git_sync_enterprise import ent_on_main
from src.infrastructure.git.git_work_commits import commit_engagement_work, push_engagement
from src.infrastructure.rest.routers import events
from src.infrastructure.rest.routers.sync.changes import list_changes
from src.infrastructure.runtime_state_ignore import ensure_runtime_state_ignored
from src.infrastructure.workspace.mutation_gate import _reset_for_test
from tests.support.git_workflow_fixtures import git as _git
from tests.support.git_workflow_fixtures import valid_entity_md

_REQUIREMENTS = "model/motivation/requirement"
LEGACY_ENTITY = f"{_REQUIREMENTS}/REQ@1000000911.PullLg.kept-under-model.md"
GROUPED_ENTITY = f"projects/p/{_REQUIREMENTS}/REQ@1000000912.PullGr.kept-under-projects.md"
SCRATCHPAD = "scratchpads/p/SCR@1000000913.PullSc.shared-thinking.scratchpad.yaml"
UNRELATED = f"{_REQUIREMENTS}/REQ@1000000914.PullUn.our-own-unrelated-work.md"
ADDED_BY_THEM = f"projects/p/{_REQUIREMENTS}/REQ@1000000915.PullNw.added-by-a-teammate.md"
DOOMED = f"projects/p/{_REQUIREMENTS}/REQ@1000000916.PullDl.deleted-by-a-teammate.md"
MOVED_FROM = f"projects/p/{_REQUIREMENTS}/REQ@1000000917.PullMv.moved-by-a-teammate.md"
MOVED_TO = f"projects/q/{_REQUIREMENTS}/REQ@1000000917.PullMv.moved-by-a-teammate.md"
CONFIGURATION = ".arch-repo/viewpoint-pins.yaml"
REVISED = "Revised By A Teammate"


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

    def as_published(self) -> Path:
        """A fresh clone of the remote: what anyone else now receives."""
        return _clone(self.remote, self.remote.parent / "as-published")


@pytest.fixture
def pair(tmp_path: Path) -> Pair:
    """A bare remote and two clones of it, each holding both layouts, a scratchpad and configuration."""
    _reset_for_test()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", "--quiet", str(remote)], check=True)
    seed = _clone(remote, tmp_path / "seed")
    _git(seed, "checkout", "-q", "-b", "main")
    _write(seed, LEGACY_ENTITY, _entity(LEGACY_ENTITY, "As First Written"))
    _write(seed, GROUPED_ENTITY, _entity(GROUPED_ENTITY, "As First Written"))
    _write(seed, SCRATCHPAD, _scratchpad("As first written"))
    _write(seed, DOOMED, _entity(DOOMED, "Deleted By A Teammate"))
    _write(seed, MOVED_FROM, _entity(MOVED_FROM, "Moved By A Teammate"))
    _write(seed, CONFIGURATION, "pins: []\n")
    # As a scaffolded repository has it: tracked from the first commit.
    ensure_runtime_state_ignored(seed)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "-u", "origin", "main")
    return Pair(remote, _clone(remote, tmp_path / "ours"), _clone(remote, tmp_path / "theirs"))


def _a_teammate_publishes(pair: Pair) -> None:
    """The teammate changes content of every kind — edits, an addition, a deletion, a move between
    groups, the repository's configuration — saves, and pushes."""
    _write(pair.theirs, LEGACY_ENTITY, _entity(LEGACY_ENTITY, REVISED))
    _write(pair.theirs, GROUPED_ENTITY, _entity(GROUPED_ENTITY, REVISED))
    _write(pair.theirs, SCRATCHPAD, _scratchpad(REVISED))
    _write(pair.theirs, ADDED_BY_THEM, _entity(ADDED_BY_THEM, "Added By A Teammate"))
    _write(pair.theirs, CONFIGURATION, f"pins: []\n# {REVISED}\n")
    (pair.theirs / DOOMED).unlink()
    (pair.theirs / MOVED_TO).parent.mkdir(parents=True)
    (pair.theirs / MOVED_FROM).rename(pair.theirs / MOVED_TO)
    commit_engagement_work(pair.theirs, "revise the requirement and the pad")
    push_engagement(pair.theirs)


def _poll(repo: Path) -> None:
    asyncio.run(GitSyncManager([RepoSpec(repo, "engagement")])._sync_engagement(repo))


def _we_pull(pair: Pair) -> None:
    _poll(pair.ours)
    assert _git(pair.ours, "rev-parse", "HEAD") == _git(pair.remote, "rev-parse", "main"), (
        "the pull did not happen at all, so nothing below is about it"
    )


def _shows_the_teammates_work(repo: Path) -> dict[str, bool]:
    """Each thing the teammate did, and whether this working tree shows it."""

    def reads(rel: str) -> str:
        path = repo / rel
        return path.read_text(encoding="utf-8") if path.exists() else ""

    return {
        "edit under model/": REVISED in reads(LEGACY_ENTITY),
        "edit under projects/": REVISED in reads(GROUPED_ENTITY),
        "edit under scratchpads/": REVISED in reads(SCRATCHPAD),
        "edit under .arch-repo/": REVISED in reads(CONFIGURATION),
        "addition": (repo / ADDED_BY_THEM).exists(),
        "deletion": not (repo / DOOMED).exists(),
        "move": (repo / MOVED_TO).exists() and not (repo / MOVED_FROM).exists(),
    }


_ALL_OF_IT = dict.fromkeys(
    (
        "edit under model/",
        "edit under projects/",
        "edit under scratchpads/",
        "edit under .arch-repo/",
        "addition",
        "deletion",
        "move",
    ),
    True,
)
_NONE_OF_IT = dict.fromkeys(_ALL_OF_IT, False)


def _raw_status(repo: Path) -> str:
    """Git's own unfiltered answer, untracked files included — not the product's reading of it."""
    return _git(repo, "status", "--porcelain", "-u")


@pytest.fixture
def published_events(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    async def record(event: dict) -> None:
        seen.append(event)

    monkeypatch.setattr(events.event_bus, "publish", record)
    return seen


class TestAFastForward:
    def test_it_installs_everything_the_commit_changed(self, pair: Pair) -> None:
        _a_teammate_publishes(pair)

        _we_pull(pair)

        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT

    def test_it_leaves_a_clean_clone_clean(self, pair: Pair) -> None:
        """Nothing modified, nothing deleted, nothing left behind untracked — by git's own account
        and by each of the product's readings of it."""
        _a_teammate_publishes(pair)

        _we_pull(pair)

        assert _raw_status(pair.ours) == ""
        assert has_uncommitted_changes(pair.ours) is False
        assert list_changes(pair.ours) == []

    def test_the_save_after_it_does_not_undo_the_teammates_work(self, pair: Pair) -> None:
        _a_teammate_publishes(pair)
        _we_pull(pair)

        _write(pair.ours, UNRELATED, _entity(UNRELATED, "Our Own Unrelated Work"))
        commit_engagement_work(pair.ours, "add an unrelated requirement")
        push_engagement(pair.ours)

        published = pair.as_published()
        assert (published / UNRELATED).exists(), "our own work did not reach the remote"
        assert _shows_the_teammates_work(published) == _ALL_OF_IT
        assert _git(pair.remote, "show", "--name-only", "--format=", "main").splitlines() == [UNRELATED]


class TestARebase:
    """We hold a commit the remote does not, so the pull replays it onto the teammate's."""

    def _we_commit_our_own(self, pair: Pair) -> None:
        _write(pair.ours, UNRELATED, _entity(UNRELATED, "Our Own Unrelated Work"))
        commit_engagement_work(pair.ours, "add an unrelated requirement")

    def test_it_installs_everything_and_keeps_our_commit(self, pair: Pair) -> None:
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)

        _poll(pair.ours)

        assert _git(pair.ours, "rev-list", "--count", "HEAD..origin/main") == "0", "the pull did not happen"
        assert _git(pair.ours, "rev-list", "--count", "origin/main..HEAD") == "1"
        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT
        assert (pair.ours / UNRELATED).exists()
        assert _raw_status(pair.ours) == ""

    def test_our_push_after_it_publishes_both(self, pair: Pair) -> None:
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)
        _poll(pair.ours)

        push_engagement(pair.ours)

        published = pair.as_published()
        assert (published / UNRELATED).exists()
        assert _shows_the_teammates_work(published) == _ALL_OF_IT

    def test_it_refuses_to_replace_unsaved_work_and_touches_nothing(
        self, pair: Pair, published_events: list[dict],
    ) -> None:
        """Ahead of the remote, the pull runs whatever the tree holds — so the refusal is the
        publisher's own. The file the teammate also changed keeps our unsaved text, the branch stays
        where it was, nothing else of theirs is half-installed, and the author is told which file."""
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)
        before = _git(pair.ours, "rev-parse", "HEAD")
        _write(pair.ours, GROUPED_ENTITY, _entity(GROUPED_ENTITY, "Our Unsaved Thought"))

        _poll(pair.ours)

        assert "Our Unsaved Thought" in (pair.ours / GROUPED_ENTITY).read_text(encoding="utf-8")
        assert _git(pair.ours, "rev-parse", "HEAD") == before
        assert _shows_the_teammates_work(pair.ours) == _NONE_OF_IT
        assert _raw_status(pair.ours).split() == ["M", GROUPED_ENTITY]
        conflicts = [event for event in published_events if event["type"] == "sync_conflict"]
        assert len(conflicts) == 1 and GROUPED_ENTITY in conflicts[0]["error"]

    def test_it_refuses_to_replace_an_unsaved_file_at_a_path_the_teammate_added(self, pair: Pair) -> None:
        """Untracked on our side, added on theirs: neither is the other's to overwrite."""
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)
        _write(pair.ours, ADDED_BY_THEM, _entity(ADDED_BY_THEM, "Ours Under The Same Name"))

        _poll(pair.ours)

        assert "Ours Under The Same Name" in (pair.ours / ADDED_BY_THEM).read_text(encoding="utf-8")
        assert not (pair.ours / MOVED_TO).exists()

    def test_unsaved_work_the_commit_does_not_touch_stays_unsaved(self, pair: Pair) -> None:
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)
        _write(pair.ours, UNRELATED, _entity(UNRELATED, "Still Being Written"))

        _poll(pair.ours)

        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT
        assert "Still Being Written" in (pair.ours / UNRELATED).read_text(encoding="utf-8")
        assert _raw_status(pair.ours).split() == ["M", UNRELATED]

    def test_once_the_work_is_saved_the_pull_goes_through(self, pair: Pair) -> None:
        """The refusal is a deferral: nothing was lost on either side, so nothing needs repairing."""
        self._we_commit_our_own(pair)
        _a_teammate_publishes(pair)
        _write(pair.ours, LEGACY_ENTITY, _entity(LEGACY_ENTITY, "Our Unsaved Thought"))
        _poll(pair.ours)
        assert _shows_the_teammates_work(pair.ours) == _NONE_OF_IT

        _git(pair.ours, "checkout", "--", LEGACY_ENTITY)
        _poll(pair.ours)

        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT


class TestBehindWithUnsavedWork:
    def test_the_pull_waits_and_the_work_is_untouched(self, pair: Pair) -> None:
        """Behind and not ahead, a tree with unsaved work is not pulled into at all — wherever the
        work is. A scratchpad counts: the same reading that tells the status there is something to
        save tells the pull to wait."""
        _a_teammate_publishes(pair)
        before = _git(pair.ours, "rev-parse", "HEAD")
        _write(pair.ours, SCRATCHPAD, _scratchpad("Our Unsaved Thought"))

        _poll(pair.ours)

        assert _git(pair.ours, "rev-parse", "HEAD") == before
        assert "Our Unsaved Thought" in (pair.ours / SCRATCHPAD).read_text(encoding="utf-8")
        assert _shows_the_teammates_work(pair.ours) == _NONE_OF_IT

    def test_runtime_state_is_not_unsaved_work(self, pair: Pair) -> None:
        """What the deployment keeps for itself never holds a pull back."""
        _a_teammate_publishes(pair)
        _write(pair.ours, ".arch/enterprise-sync.json", "{}\n")
        _write(pair.ours, ".arch-repo/exchange-identity.json", "{}\n")
        _write(pair.ours, ".arch-repo/transactions/abandoned/intent.tmp", "{}\n")

        _we_pull(pair)

        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT


class TestTheEnterprisePull:
    """The enterprise mirror follows `origin/main` through the same publisher."""

    def test_it_installs_everything_the_commit_changed(self, pair: Pair, published_events: list[dict]) -> None:
        _a_teammate_publishes(pair)
        _git(pair.ours, "fetch", "-q", "origin")

        assessed = asyncio.run(ent_on_main(GitSyncManager([RepoSpec(pair.ours, "enterprise")]), pair.ours))

        assert assessed is True
        assert "sync_pull_completed" in [event["type"] for event in published_events]
        assert _git(pair.ours, "rev-parse", "HEAD") == _git(pair.remote, "rev-parse", "main")
        assert _shows_the_teammates_work(pair.ours) == _ALL_OF_IT
        assert _raw_status(pair.ours) == ""
