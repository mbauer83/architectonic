"""Regression coverage for the cross-scope index-staleness bug.

Two independently-cached `ArtifactIndex` singletons can exist for the same physical engagement
repo — one scoped to the engagement repo alone (e.g. `edit_tools.py`'s standalone MCP write
tools), one scoped to engagement+enterprise combined (the REST/GUI layer's global `_repo`, and
MCP reads that default to `repo_scope="both"`). A write committed through one singleton's own
`ArtifactIndex.apply_file_changes` never touched the other, so e.g. `artifact_delete_entity`
(engagement-only scope) reported "not found" for an entity the GUI had just created (both-scope)
until a manual `artifact_admin_reindex`, and vice versa.

Fixed by routing every write-commit path through `notify_paths_changed` (`bootstrap.py`), which
already applies a changed path to *every* live registered index whose mounts overlap it — it was
previously wired only for git-sync-driven external changes, never for the app's own writes.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp.context import apply_authoritative_changes


def _write_entity(path: Path, artifact_id: str, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: goal\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"## {name}\n",
        encoding="utf-8",
    )


def test_engagement_scoped_write_is_visible_to_a_live_combined_scope_index(tmp_path: Path) -> None:
    engagement = tmp_path / "engagement"
    enterprise = tmp_path / "enterprise"
    engagement.mkdir(parents=True)
    enterprise.mkdir(parents=True)

    # Simulates the REST/GUI layer's global, engagement+enterprise-combined index, already live
    # before the write happens (mirrors backend startup order).
    combined = shared_artifact_index([engagement, enterprise])
    combined.refresh()
    # Simulates edit_tools.py's separate, engagement-only-scoped index.
    engagement_only = shared_artifact_index([engagement])
    engagement_only.refresh()

    entity_path = engagement / "model" / "motivation" / "goal" / "GOL@1.new.new.md"
    _write_entity(entity_path, "GOL@1.new.new", "New Goal")

    # Simulates edit_tools.py's post-write notification: apply_authoritative_changes(paths, [engagement]).
    apply_authoritative_changes([entity_path], [engagement])

    assert engagement_only.get_entity("GOL@1.new.new") is not None
    assert combined.get_entity("GOL@1.new.new") is not None


def test_combined_scope_write_is_visible_to_a_live_engagement_only_index(tmp_path: Path) -> None:
    engagement = tmp_path / "engagement"
    enterprise = tmp_path / "enterprise"
    engagement.mkdir(parents=True)
    enterprise.mkdir(parents=True)

    engagement_only = shared_artifact_index([engagement])
    engagement_only.refresh()
    combined = shared_artifact_index([engagement, enterprise])
    combined.refresh()

    entity_path = engagement / "model" / "motivation" / "goal" / "GOL@2.rest.rest.md"
    _write_entity(entity_path, "GOL@2.rest.rest", "REST-Created Goal")

    # Simulates the GUI/REST write path: apply_authoritative_changes(paths, [engagement, enterprise]).
    apply_authoritative_changes([entity_path], [engagement, enterprise])

    assert combined.get_entity("GOL@2.rest.rest") is not None
    assert engagement_only.get_entity("GOL@2.rest.rest") is not None
