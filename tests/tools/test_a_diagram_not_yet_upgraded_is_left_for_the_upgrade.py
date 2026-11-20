"""A diagram stored before groupings had ids is converted by the repository upgrade and by nothing else.

A format change is the upgrade's to make: it is rehearsed, reported, committed as one step, and made
only for the tiers a deployment owns. A sync or an edit that gave such a diagram its ids on the way
past would make that change unannounced, in whichever repository it happened to be pointed at.

The line: a grouping a caller *states now* without an id is new, and the write gives it one. A
grouping a *file holds* without an id is content of the earlier format; no write stores it again and
none converts it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.application.modeling.artifact_write import generate_diagram_id
from src.application.repository_upgrade.steps.diagram_identity_keys import DiagramIdentityKeysStep
from src.domain.diagrams.authored_groupings import grouping_ids
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


class _NotYetUpgraded:
    """A grouped diagram as a release before grouping ids left it: written by the tools, ids taken out."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        made = mcp.artifact_create_entity(
            artifact_type="application-component", name="Portal", summary="A portal", dry_run=False,
            repo_root=str(repo),
        )
        self.portal = str(made["artifact_id"])
        self.id = generate_diagram_id("archimate-application", "An Older View")
        created = mcp.artifact_create_diagram(
            diagram_type="archimate-application", name="An Older View", artifact_id=self.id,
            entity_ids=[self.portal], authored_groupings=[{"label": "Front", "entity-ids": [self.portal]}],
            dry_run=False, repo_root=str(repo),
        )
        assert created["wrote"], created
        self.path = Path(str(created["path"]))
        text = self.path.read_text(encoding="utf-8")
        older = re.sub(r"^- id: g-\w+\n  label:", "- label:", text, flags=re.MULTILINE)
        assert older != text
        self.path.write_text(older, encoding="utf-8")
        self.stored = self.path.read_bytes()

    @property
    def groupings(self) -> object:
        return parse_frontmatter(self.path.read_text(encoding="utf-8")).get("authored-groupings")

    def upgrade(self) -> None:
        step, view = DiagramIdentityKeysStep(), FilesystemRepoUpgradeView(self.repo)
        step.apply(view, FilesystemRepoUpgradeWriter(self.repo), step.detect(view))


def test_a_sync_leaves_it_byte_for_byte_and_says_what_to_run(repo: Path) -> None:
    older = _NotYetUpgraded(repo)

    result = mcp.artifact_edit_diagram(artifact_id=older.id, puml="auto-sync", dry_run=False, repo_root=str(repo))

    assert not result["wrote"]
    assert older.path.read_bytes() == older.stored
    assert any("arch-repair upgrade" in warning for warning in result["warnings"])
    assert [issue["code"] for issue in result["verification"]["issues"]] == ["E373"]


@pytest.mark.parametrize(
    "edit",
    [
        {"name": "Renamed"},
        {"status": "active"},
        {"authored_groupings": [{"label": "Front", "entity-ids": ["<portal>"]}]},
        {"authored_groupings": []},
        {"entity_ids": ["<portal>"]},
    ],
    ids=["rename", "status", "restating-the-groupings", "removing-the-groupings", "restating-membership"],
)
def test_a_direct_edit_is_refused_with_the_upgrade_sentence_whatever_it_states(
    repo: Path, edit: dict[str, object]
) -> None:
    """Restating the groupings included: sending back what was read cannot be told from stating anew."""
    older = _NotYetUpgraded(repo)
    stated = {
        key: [{**item, "entity-ids": [older.portal]} if isinstance(item, dict) else older.portal for item in value]
        if isinstance(value, list) else value
        for key, value in edit.items()
    }

    with pytest.raises(ValueError, match="arch-repair upgrade"):
        mcp.artifact_edit_diagram(artifact_id=older.id, dry_run=False, repo_root=str(repo), **stated)  # type: ignore[arg-type]

    assert older.path.read_bytes() == older.stored


def test_after_the_upgrade_step_both_proceed_and_the_ids_are_the_upgrade_s(repo: Path) -> None:
    older = _NotYetUpgraded(repo)

    older.upgrade()

    (given,) = grouping_ids(older.groupings)
    synced = mcp.artifact_edit_diagram(artifact_id=older.id, puml="auto-sync", dry_run=False, repo_root=str(repo))
    assert "E373" not in [issue["code"] for issue in synced["verification"]["issues"]]
    assert not any("arch-repair upgrade" in warning for warning in synced["warnings"])
    edited = mcp.artifact_edit_diagram(artifact_id=older.id, status="active", dry_run=False, repo_root=str(repo))
    assert edited["wrote"], edited
    assert grouping_ids(older.groupings) == (given,)


def test_a_grouping_stated_now_without_an_id_is_new_and_is_given_one(repo: Path) -> None:
    """The other side of the line: minting for what a caller states is the write path's job."""
    older = _NotYetUpgraded(repo)
    older.upgrade()

    added = mcp.artifact_edit_diagram(
        artifact_id=older.id, dry_run=False, repo_root=str(repo),
        authored_groupings=[*older.groupings, {"label": "Added", "entity-ids": []}],  # type: ignore[misc]
    )

    assert added["wrote"], added
