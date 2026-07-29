"""A rename and its referrer rewrites are one fact, and drift heals rather than sticking.

The slug tail of an artifact id is a human-readable hint; identity is the
``PREFIX@epoch.random`` stem. That leniency is deliberate — every resolver accepts a stale
slug — but it means a referrer left naming an old slug still resolves, so nothing downstream
complains and the drift accumulates unseen. Two properties keep it from doing so:

* renaming rewrites every referrer in the same transaction as the rename, so the two cannot
  come apart;
* the search keys on the stem, not on the id being renamed *from*, so a referrer holding any
  older slug is found and healed rather than being permanently unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write._entity_rename import plan_referrer_rewrites


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-RENAME" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, conn_type: str = "archimate-realization") -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=conn_type,
        description="Realizes it.", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result


def _rename(repo: Path, artifact_id: str, new_name: str) -> str:
    result = mcp.artifact_edit_entity(
        artifact_id=artifact_id, name=new_name, dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _referrer_text(repo: Path, source_id: str) -> str:
    path = next(repo.rglob(f"{source_id}.outgoing.md"))
    return path.read_text(encoding="utf-8")


class TestRenameRewritesReferrers:
    def test_a_referrer_names_the_new_slug(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Source Requirement")
        target = _entity(repo, "outcome", "Original Target Name")
        _connect(repo, source, target)

        renamed = _rename(repo, target, "Renamed Target")

        text = _referrer_text(repo, source)
        assert renamed in text
        assert target not in text

    def test_the_rewrite_is_committed_with_the_rename(self, repo: Path) -> None:
        """Returned paths are the transaction's, so the referrer is part of the commit."""
        source = _entity(repo, "requirement", "Committed Source")
        target = _entity(repo, "outcome", "Committed Target")
        _connect(repo, source, target)
        referrer = next(repo.rglob(f"{source}.outgoing.md"))

        result = mcp.artifact_edit_entity(
            artifact_id=target, name="Committed Renamed", dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"] is True
        assert referrer.exists()
        assert str(result["artifact_id"]) in referrer.read_text(encoding="utf-8")

    def test_several_referrers_are_all_rewritten(self, repo: Path) -> None:
        target = _entity(repo, "outcome", "Shared Target")
        sources = [_entity(repo, "requirement", f"Referrer {n}") for n in range(3)]
        for source in sources:
            _connect(repo, source, target)

        renamed = _rename(repo, target, "Shared Target Renamed")

        for source in sources:
            assert renamed in _referrer_text(repo, source)


class TestDriftHealsRatherThanSticking:
    def test_a_referrer_holding_an_older_slug_is_still_found(self, repo: Path) -> None:
        """Keying the search on the id being renamed *from* would miss this one forever."""
        source = _entity(repo, "requirement", "Healing Source")
        target = _entity(repo, "outcome", "First Name")
        _connect(repo, source, target)

        # Simulate a referrer that a previous rename failed to rewrite: it names the entity
        # by a slug that is neither the current one nor the one the next rename starts from.
        referrer = next(repo.rglob(f"{source}.outgoing.md"))
        stem = target.rsplit(".", 1)[0]
        referrer.write_text(
            referrer.read_text(encoding="utf-8").replace(target, f"{stem}.some-ancient-slug"),
            encoding="utf-8",
        )

        renamed = _rename(repo, target, "Second Name")

        text = referrer.read_text(encoding="utf-8")
        assert renamed in text
        assert "some-ancient-slug" not in text

    def test_the_plan_matches_any_slug_for_the_same_entity(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Plan Source")
        target = _entity(repo, "outcome", "Plan Target")
        _connect(repo, source, target)
        referrer = next(repo.rglob(f"{source}.outgoing.md"))
        stem = target.rsplit(".", 1)[0]
        referrer.write_text(
            referrer.read_text(encoding="utf-8").replace(target, f"{stem}.whatever-it-used-to-be"),
            encoding="utf-8",
        )

        plan = plan_referrer_rewrites(repo_root=repo, new_artifact_id=target)

        assert referrer in plan
        assert target in plan[referrer]
        assert "whatever-it-used-to-be" not in plan[referrer]

    def test_a_repo_already_consistent_plans_no_rewrites(self, repo: Path) -> None:
        source = _entity(repo, "requirement", "Consistent Source")
        target = _entity(repo, "outcome", "Consistent Target")
        _connect(repo, source, target)

        assert plan_referrer_rewrites(repo_root=repo, new_artifact_id=target) == {}
