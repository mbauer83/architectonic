"""Signal-snapshot domain contract: the transition table, the normative idempotent
replay table (failed is terminal — replay returns, never resumes), canonical
digest stability under input reordering, and directness classification."""

from __future__ import annotations

import pytest

from src.domain.assurance.security_signal_snapshot import (
    CreateNewSnapshot,
    IdempotencyConflict,
    ReplayInProgress,
    ReplayStoredFailure,
    ReplayStoredSuccess,
    StoredSnapshotKey,
    canonical_bundle_digest,
    classify_directness,
    is_allowed_transition,
    replay_decision,
    transition_error,
)


class TestTransitionTable:
    @pytest.mark.parametrize(("current", "target"), [
        ("staging", "complete"),
        ("staging", "failed"),
        ("complete", "active"),
        ("active", "superseded"),
    ])
    def test_allowed(self, current: str, target: str) -> None:
        assert is_allowed_transition(current, target)

    @pytest.mark.parametrize(("current", "target"), [
        ("staging", "active"),      # activation only from complete
        ("complete", "superseded"),
        ("failed", "staging"),      # terminal — never resumes
        ("failed", "complete"),
        ("superseded", "active"),   # no reactivation via transition
        ("active", "failed"),
        ("complete", "failed"),
    ])
    def test_forbidden(self, current: str, target: str) -> None:
        assert not is_allowed_transition(current, target)
        assert current in transition_error(current, target)


class TestReplayTable:
    def _key(self, status: str, digest: str = "d1") -> StoredSnapshotKey:
        return StoredSnapshotKey(snapshot_id="SNAP@1", status=status, request_payload_digest=digest)

    def test_no_existing_key_creates(self) -> None:
        assert isinstance(replay_decision(None, "d1"), CreateNewSnapshot)

    def test_same_digest_staging_and_complete_are_in_progress(self) -> None:
        assert replay_decision(self._key("staging"), "d1") == ReplayInProgress(snapshot_id="SNAP@1")
        assert replay_decision(self._key("complete"), "d1") == ReplayInProgress(snapshot_id="SNAP@1")

    def test_same_digest_active_and_superseded_return_stored_success(self) -> None:
        assert replay_decision(self._key("active"), "d1") == ReplayStoredSuccess(snapshot_id="SNAP@1")
        assert replay_decision(self._key("superseded"), "d1") == ReplayStoredSuccess(snapshot_id="SNAP@1")

    def test_same_digest_failed_returns_stored_failure(self) -> None:
        assert replay_decision(self._key("failed"), "d1") == ReplayStoredFailure(snapshot_id="SNAP@1")

    def test_different_digest_is_a_typed_conflict_regardless_of_status(self) -> None:
        for status in ("staging", "complete", "active", "superseded", "failed"):
            decision = replay_decision(self._key(status), "d2")
            assert decision == IdempotencyConflict(
                snapshot_id="SNAP@1", stored_digest="d1", submitted_digest="d2",
            )


class TestCanonicalDigest:
    def test_reordering_inputs_yields_the_same_digest(self) -> None:
        a = {
            "anchor": "APP@1",
            "components": [
                {"purl": "pkg:pypi/b@2", "name": "b"},
                {"purl": "pkg:pypi/a@1", "name": "a"},
            ],
            "diagnostics": {"unmatched": 0, "skipped": 0},
        }
        b = {
            "diagnostics": {"skipped": 0, "unmatched": 0},
            "components": [
                {"name": "a", "purl": "pkg:pypi/a@1"},
                {"name": "b", "purl": "pkg:pypi/b@2"},
            ],
            "anchor": "APP@1",
        }
        assert canonical_bundle_digest(a) == canonical_bundle_digest(b)

    def test_semantic_field_change_changes_the_digest(self) -> None:
        base = {"anchor": "APP@1", "components": [{"purl": "pkg:pypi/a@1"}]}
        changed = {"anchor": "APP@1", "components": [{"purl": "pkg:pypi/a@2"}]}
        assert canonical_bundle_digest(base) != canonical_bundle_digest(changed)

    def test_digest_is_stable_hex_sha256(self) -> None:
        digest = canonical_bundle_digest({"anchor": "APP@1"})
        assert len(digest) == 64
        assert digest == canonical_bundle_digest({"anchor": "APP@1"})


class TestDirectness:
    EDGES = [
        ("root", "a"), ("a", "b"), ("b", "c"),
        ("c", "a"),  # cycle back into the graph
        ("orphan-parent", "orphan"),
    ]

    def test_depth_one_is_direct(self) -> None:
        assert classify_directness("root", "a", self.EDGES) == "direct"

    def test_deeper_reachable_is_transitive(self) -> None:
        assert classify_directness("root", "b", self.EDGES) == "transitive"
        assert classify_directness("root", "c", self.EDGES) == "transitive"

    def test_unreachable_is_unknown_and_cycles_terminate(self) -> None:
        assert classify_directness("root", "orphan", self.EDGES) == "unknown"
        assert classify_directness("root", "missing", self.EDGES) == "unknown"

    def test_the_root_is_not_a_dependency(self) -> None:
        assert classify_directness("root", "root", self.EDGES) == "unknown"
