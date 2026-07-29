"""Guards the point that made the prior multi-instance design's duplication possible in the
first place: combined views must live in their own cache, never in `_services` (the dict
`notify_paths_changed` broadcasts writes across) — and a request for a given root pair must
never allocate more than the two canonical single-root instances it's built from.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.infrastructure.artifact_index import (
    bootstrap,
    combined_artifact_index,
    notify_paths_changed,
    shared_artifact_index,
)
from src.infrastructure.artifact_index.service import ArtifactIndex

from ._combined_fixtures import build_two_repo_fixture, write_entity


def test_combined_view_never_lives_in_the_broadcast_cache(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)

    assert combined not in bootstrap._services.values()
    assert combined in bootstrap._combined_views.values()


def test_notify_paths_changed_never_calls_a_method_on_a_combined_view(tmp_path: Path, monkeypatch) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    spy = MagicMock(wraps=combined.refresh)
    monkeypatch.setattr(combined, "refresh", spy)

    new_entity = engagement / "model" / "motivation" / "requirement" / "REQ@9.new.new.md"
    write_entity(new_entity, "REQ@9.new.new", "New Entity")
    notify_paths_changed([new_entity])

    spy.assert_not_called()


def test_requesting_engagement_enterprise_and_combined_allocates_exactly_two_instances(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    before = len(bootstrap._services)

    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    combined = combined_artifact_index(engagement, enterprise)

    assert len(bootstrap._services) - before == 2
    assert combined._engagement is eng_only  # type: ignore[attr-defined]
    assert combined._enterprise is ent_only  # type: ignore[attr-defined]


def test_services_cache_never_holds_a_non_artifact_index_value(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    shared_artifact_index(engagement)
    shared_artifact_index(enterprise)
    combined_artifact_index(engagement, enterprise)

    assert all(isinstance(value, ArtifactIndex) for value in bootstrap._services.values())
