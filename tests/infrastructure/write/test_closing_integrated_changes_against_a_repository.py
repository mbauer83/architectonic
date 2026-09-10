"""The sweep, bound to real repositories: it closes a change and tells the index it did.

`integration_sweep` decides; this is the adapter that reads enterprise artifacts and writes proposal
state. Three things it must get right that the decision cannot: the proposal has to be *findable* —
a `proposed-change` is an internal type, and a repository that excluded internal types from listing
would sweep nothing while reporting success — every closed proposal has to reach the index, or the
next read reports it as still submitted, and the artifact has to be read from **upstream**.

The fixture is a real pair with a real bare origin, with the target in the enterprise repository
where it belongs. It used to put the enterprise artifact in the *engagement* root and read it from
there, which is the confusion that let a submission's own replay count as somebody accepting it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
from src.infrastructure.write.artifact_write.integration_cleanup import close_integrated_changes
from tests.support.git_workflow_fixtures import (
    ENT_ENTITY_ID,
    build_workflow_pair,
    git,
    valid_entity_md,
)

TARGET = ENT_ENTITY_ID
PROPOSAL = "PCH@1780000002.ccccccc.rename-it"


def _proposal_md(state: str, proposed_name: str) -> str:
    return (
        "---\n"
        f"artifact-id: {PROPOSAL}\n"
        "artifact-type: proposed-change\n"
        "name: rename it\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        f"proposes-change-to: {TARGET}\n"
        f"proposal-state: {state}\n"
        "base-revision: abc1234\n"
        "recorded-edit:\n"
        "  kind: entity\n"
        f"  artifact-id: {TARGET}\n"
        "  fields:\n"
        f"    name: {proposed_name}\n"
        "---\n\n<!-- §content -->\n\n## Rename it\n\nBecause.\n"
    )


@pytest.fixture()
def repo_at(tmp_path: Path):
    def build(*, upstream_name: str, state: str = "submitted", proposed_name: str = "Payments Platform"):
        """A pair whose `origin/main` says `upstream_name`, holding one proposal asking for another."""
        engagement, enterprise = build_workflow_pair(tmp_path)
        target = enterprise / "model" / "motivation" / "requirement" / f"{TARGET}.md"
        target.write_text(valid_entity_md(TARGET, upstream_name), encoding="utf-8")
        git(enterprise, "add", "model")
        git(enterprise, "commit", "-m", "what upstream says")
        git(enterprise, "push", "origin", "main")

        proposal_dir = engagement / "model" / "common" / "proposed-change"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{PROPOSAL}.md"
        proposal_path.write_text(_proposal_md(state, proposed_name), encoding="utf-8")

        index = combined_artifact_index(engagement, enterprise)
        repository = ArtifactRepository(
            index,
            excluded_entity_types=process_runtime_catalogs().ontology.entity_types_with_class("internal"),
        )
        repository.refresh()
        return repository, proposal_path

    return build


def test_the_proposal_is_findable_even_though_its_type_is_internal(repo_at) -> None:
    """The failure that would make the whole sweep silently do nothing."""
    repository, _ = repo_at(upstream_name="Payments")

    assert [r.artifact_id for r in repository.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)] == [PROPOSAL]


def test_a_change_the_artifact_now_carries_is_closed_on_disk(repo_at) -> None:
    repository, proposal_path = repo_at(upstream_name="Payments Platform")

    report = close_integrated_changes(repository)

    assert [c.proposal_id for c in report.closed] == [PROPOSAL]
    assert "proposal-state: integrated" in proposal_path.read_text(encoding="utf-8")


def test_the_index_is_told_so_the_next_read_agrees(repo_at) -> None:
    """A state written straight to disk leaves every cached index holding the old value."""
    repository, _ = repo_at(upstream_name="Payments Platform")

    close_integrated_changes(repository)
    reread = repository.get_entity(PROPOSAL)

    assert reread is not None
    assert reread.extra["proposal-state"] == "integrated"


def test_a_change_still_awaiting_review_is_untouched(repo_at) -> None:
    repository, proposal_path = repo_at(upstream_name="Payments")
    before = proposal_path.read_bytes()

    report = close_integrated_changes(repository)

    assert report.closed == ()
    assert proposal_path.read_bytes() == before


def test_a_second_pass_changes_nothing(repo_at) -> None:
    """It runs on every startup and after every fetch, so it must be free when there is nothing to do."""
    repository, proposal_path = repo_at(upstream_name="Payments Platform")
    close_integrated_changes(repository)
    after_first = proposal_path.read_bytes()

    second = close_integrated_changes(repository)

    assert second.closed == ()
    assert proposal_path.read_bytes() == after_first


# ── the branch goes when the last change on it does ──────────────────────────


def _retire(repo, monkeypatch, *, pending: bool = True, upstream_holds_it: bool = True):  # noqa: ANN001, ANN202
    """Run the retirement with the git side observed rather than performed.

    The conditions are the behaviour; whether `git push --delete` works is
    `enterprise_branch_lifecycle`'s own test. Faking it here is what lets each condition be stated
    on its own instead of behind a real remote.
    """
    from src.infrastructure.git import (
        enterprise_branch_lifecycle,
        enterprise_sync_state,
        git_repository_state,
    )
    from src.infrastructure.write.artifact_write import integration_cleanup

    abandoned: list[Path] = []
    monkeypatch.setattr(
        enterprise_branch_lifecycle, "abandon_enterprise_branch",
        lambda root: (abandoned.append(root), "arch/work-1")[1],
    )
    monkeypatch.setattr(
        enterprise_sync_state, "load",
        lambda _root: type("S", (), {"is_pending": lambda self: pending, "branch": "arch/work-1"})(),
    )
    monkeypatch.setattr(
        git_repository_state, "content_is_upstream", lambda *_a, **_k: upstream_holds_it
    )
    return integration_cleanup._retire_a_finished_review_branch(repo), abandoned  # noqa: SLF001


@pytest.fixture()
def enterprise_mounted(tmp_path: Path, monkeypatch):  # noqa: ANN001, ANN201
    """A repository whose mounts include an enterprise root, which is what the retirement needs."""
    process_runtime_catalogs()
    engagement = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (engagement / "model" / "common" / "proposed-change").mkdir(parents=True)
    enterprise = tmp_path / "enterprise-repository"
    (enterprise / "model").mkdir(parents=True)
    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    return engagement, enterprise, ArtifactRepository(index)


def test_the_branch_is_retired_once_nothing_live_remains(enterprise_mounted, monkeypatch) -> None:  # noqa: ANN001
    _engagement, enterprise, repo = enterprise_mounted

    retired, abandoned = _retire(repo, monkeypatch)

    assert retired == "arch/work-1"
    assert abandoned == [enterprise]


def test_a_branch_still_carrying_a_live_change_is_left_alone(enterprise_mounted, monkeypatch) -> None:  # noqa: ANN001
    """One integrated change does not empty a branch that is carrying another."""
    engagement, _enterprise, repo = enterprise_mounted
    (engagement / "model" / "common" / "proposed-change" / f"{PROPOSAL}.md").write_text(
        _proposal_md("submitted", "Payments Platform"), encoding="utf-8"
    )
    repo.refresh()

    retired, abandoned = _retire(repo, monkeypatch)

    assert retired is None
    assert abandoned == []


def test_a_branch_carrying_work_upstream_lacks_is_left_alone(enterprise_mounted, monkeypatch) -> None:  # noqa: ANN001
    """The condition that makes this safe. "No change is still pending" is not "the branch is
    finished": the same branch carries promotions, which are not changes and have their own review,
    and deleting it from the remote on the change count alone would take them with it."""
    _engagement, _enterprise, repo = enterprise_mounted

    retired, abandoned = _retire(repo, monkeypatch, upstream_holds_it=False)

    assert retired is None
    assert abandoned == []


def test_an_accumulating_branch_is_never_taken_down(enterprise_mounted, monkeypatch) -> None:  # noqa: ANN001
    """The guard that matters most: an accumulating branch carries promoted work nobody has
    submitted, and abandoning it would destroy it."""
    _engagement, _enterprise, repo = enterprise_mounted

    retired, abandoned = _retire(repo, monkeypatch, pending=False)

    assert retired is None
    assert abandoned == []


def test_a_repository_with_no_enterprise_mount_has_no_branch_to_retire(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """The ordinary engagement deployment: there is no enterprise repository here, so there is
    nothing of its lifecycle to reach."""
    process_runtime_catalogs()
    engagement = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (engagement / "model" / "common" / "proposed-change").mkdir(parents=True)
    index = shared_artifact_index(engagement)
    index.refresh()

    retired, abandoned = _retire(ArtifactRepository(index), monkeypatch)

    assert retired is None
    assert abandoned == []
