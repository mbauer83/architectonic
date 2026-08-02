"""Identity/duplicate-id coverage for CombinedArtifactView.

Three distinct cases, deliberately kept separate — each is a different way the duplicate-id
guarantee can be broken, and collapsing them would hide which one regressed:

1. `scan_duplicate_short_ids` must concatenate, not dict-overwrite, when the *same* short id
   is independently already a within-scope duplicate on both sides.
2. `cross_repo_duplicate_ids`/the startup check must fail closed on a *persistent* full-id
   collision across repos (never legitimate outside promotion's transient window).
3. During promotion's transient copy-then-unlink window, the same persistent-looking state is
   expected and must NOT raise — `get_entity` must resolve deterministically (engagement-first)
   instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index

from ._combined_fixtures import ENG_B, build_two_repo_fixture, write_entity


def test_find_all_by_stable_id_concatenates_candidates_from_both_repos(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    eng_only = shared_artifact_index(engagement)
    ent_only = shared_artifact_index(enterprise)
    eng_only.refresh()
    ent_only.refresh()
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    short = stable_id(ENG_B)
    expected = [*eng_only.find_all_by_stable_id(short), *ent_only.find_all_by_stable_id(short)]
    assert combined.find_all_by_stable_id(short) == expected
    assert len(expected) == 1  # sanity: this short id only exists on the engagement side


def test_reconcile_short_id_is_a_safe_no_op_when_nothing_is_stale(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    combined.reconcile_short_id(stable_id(ENG_B))  # must not raise


def test_scan_duplicate_short_ids_concatenates_paths_for_a_key_duplicated_on_both_sides(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    # Same short id ("REQ@7.twin"), two distinct full ids (rename-shadowing), independently on
    # *each* side — the case a naive `{**engagement_dict, **enterprise_dict}` merge would let
    # one side's path list silently overwrite the other's under the shared key.
    write_entity(engagement / "model" / "motivation" / "requirement" / "REQ@7.twin.old.md", "REQ@7.twin.old", "Old")
    write_entity(engagement / "model" / "motivation" / "requirement" / "REQ@7.twin.new.md", "REQ@7.twin.new", "New")
    write_entity(enterprise / "model" / "motivation" / "requirement" / "REQ@7.twin.a.md", "REQ@7.twin.a", "A")
    write_entity(enterprise / "model" / "motivation" / "requirement" / "REQ@7.twin.b.md", "REQ@7.twin.b", "B")

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    duplicates = combined.scan_duplicate_short_ids()
    assert "REQ@7.twin" in duplicates
    assert len(duplicates["REQ@7.twin"]) == 4


def test_cross_repo_duplicate_ids_detects_a_persistent_full_id_collision(tmp_path: Path) -> None:
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    dup_id = "REQ@8.dup.dup"
    write_entity(engagement / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Engagement Copy")
    write_entity(enterprise / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Enterprise Copy")

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert combined.cross_repo_duplicate_ids() == {dup_id}


@pytest.mark.verifies("REQ@1712870400.Kk6Ll6")
def test_startup_check_fails_closed_on_a_persistent_cross_repo_id_collision(tmp_path: Path) -> None:
    from src.infrastructure.backend._startup_id_checks import assert_no_cross_repo_id_collisions

    engagement, enterprise = build_two_repo_fixture(tmp_path)
    dup_id = "REQ@8.dup.dup"
    write_entity(engagement / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Engagement Copy")
    write_entity(enterprise / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Enterprise Copy")

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    with pytest.raises(SystemExit):
        assert_no_cross_repo_id_collisions(combined)


def test_startup_check_is_a_no_op_on_a_single_root_index(tmp_path: Path) -> None:
    from src.infrastructure.backend._startup_id_checks import assert_no_cross_repo_id_collisions

    engagement, _enterprise = build_two_repo_fixture(tmp_path)
    single = shared_artifact_index(engagement)
    single.refresh()

    assert_no_cross_repo_id_collisions(single)  # not a CombinedArtifactView — must not raise


def test_get_entity_is_deterministic_and_does_not_raise_during_a_promotion_transient_window(
    tmp_path: Path,
) -> None:
    """Simulates the window `execute_promotion` passes through between `_copy_entities` writing
    the enterprise copy and `_replace_promoted_with_gars` unlinking the engagement original —
    the same full id briefly exists as a live file in both repos. This is expected, self-
    resolving, and must not be treated as an error at the single-lookup level (only the startup
    check, which never runs mid-promotion, fails closed on the persistent form of this state)."""
    engagement, enterprise = build_two_repo_fixture(tmp_path)
    dup_id = "REQ@8.dup.dup"
    write_entity(engagement / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Engagement Copy")
    write_entity(enterprise / "model" / "motivation" / "requirement" / f"{dup_id}.md", dup_id, "Enterprise Copy")

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    result = combined.get_entity(dup_id)  # must not raise
    assert result is not None
    assert result.name == "Engagement Copy"  # deterministic: engagement checked first
