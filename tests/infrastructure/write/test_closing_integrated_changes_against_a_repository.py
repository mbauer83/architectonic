"""The sweep, bound to real repositories: it closes a change and tells the index it did.

`integration_sweep` decides; this is the adapter that reads enterprise artifacts and writes proposal
state. Two things it must get right that the decision cannot: the proposal has to be *findable* — a
`proposed-change` is an internal type, and a repository that excluded internal types from listing
would sweep nothing while reporting success — and every closed proposal has to reach the index, or
the next read reports it as still submitted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.integration_cleanup import close_integrated_changes

TARGET = "APP@1780000000.aaaaaaa.payments-service"
PROPOSAL = "PCH@1780000002.ccccccc.rename-it"


def _target_md(name: str) -> str:
    return (
        "---\n"
        f"artifact-id: {TARGET}\n"
        "artifact-type: application-component\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n<!-- §content -->\n\n"
        f"## {name}\n\nA service.\n\n## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
    )


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
    def build(*, current_name: str, state: str = "submitted", proposed_name: str = "Payments Platform"):
        root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        target_dir = root / "model" / "application" / "application-component"
        proposal_dir = root / "model" / "common" / "proposed-change"
        target_dir.mkdir(parents=True, exist_ok=True)
        proposal_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{TARGET}.md").write_text(_target_md(current_name), encoding="utf-8")
        proposal_path = proposal_dir / f"{PROPOSAL}.md"
        proposal_path.write_text(_proposal_md(state, proposed_name), encoding="utf-8")

        index = shared_artifact_index(root)
        repository = ArtifactRepository(
            index,
            excluded_entity_types=process_runtime_catalogs().ontology.entity_types_with_class("internal"),
        )
        repository.refresh()
        return repository, proposal_path

    return build


def test_the_proposal_is_findable_even_though_its_type_is_internal(repo_at) -> None:
    """The failure that would make the whole sweep silently do nothing."""
    repository, _ = repo_at(current_name="Payments")

    assert [r.artifact_id for r in repository.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)] == [PROPOSAL]


def test_a_change_the_artifact_now_carries_is_closed_on_disk(repo_at) -> None:
    repository, proposal_path = repo_at(current_name="Payments Platform")

    report = close_integrated_changes(repository)

    assert [c.proposal_id for c in report.closed] == [PROPOSAL]
    assert "proposal-state: integrated" in proposal_path.read_text(encoding="utf-8")


def test_the_index_is_told_so_the_next_read_agrees(repo_at) -> None:
    """A state written straight to disk leaves every cached index holding the old value."""
    repository, _ = repo_at(current_name="Payments Platform")

    close_integrated_changes(repository)
    reread = repository.get_entity(PROPOSAL)

    assert reread is not None
    assert reread.extra["proposal-state"] == "integrated"


def test_a_change_still_awaiting_review_is_untouched(repo_at) -> None:
    repository, proposal_path = repo_at(current_name="Payments")
    before = proposal_path.read_bytes()

    report = close_integrated_changes(repository)

    assert report.closed == ()
    assert proposal_path.read_bytes() == before


def test_a_second_pass_changes_nothing(repo_at) -> None:
    """It runs on every startup and after every fetch, so it must be free when there is nothing to do."""
    repository, proposal_path = repo_at(current_name="Payments Platform")
    close_integrated_changes(repository)
    after_first = proposal_path.read_bytes()

    second = close_integrated_changes(repository)

    assert second.closed == ()
    assert proposal_path.read_bytes() == after_first
