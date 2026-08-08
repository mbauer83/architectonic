"""Hazard analysis and coverage for incremental verification-cache validity.

The verifier is what tells a user whether their repository is sound. The cache decides
which of its answers get reused instead of recomputed, so a wrong reuse decision does not
merely slow something down — it changes the answer the product gives about correctness,
while looking exactly like a fast, healthy pass. This module is organised around that
risk rather than around the functions that carry it.

## Losses

- **L1 — A real defect is reported as clean.** The user ships, promotes or publishes a
  broken model believing it verified.
- **L2 — Verification becomes unusable in practice.** Every pass costs minutes, so people
  stop running it, and L1 follows by another route.
- **L3 — A clean model is reported as broken.** Work stops on a phantom; trust in the
  verifier erodes and its output starts being ignored — again ending in L1.

## Hazards (system states that lead to a loss)

- **H1** A cached result is reused for a file whose content has changed. → L1
- **H2** A cached result outlives the rule set that produced it. → L1
- **H3** State written by one schema is read under another. → L1 (silently wrong reuse)
  or L3 (spurious findings).
- **H4** Cache is discarded although everything relevant is unchanged. → L2
- **H5** A deletion or addition leaves the result set out of step with the file set. → L1/L3.
- **H6** Partial or corrupt state is treated as authoritative. → L1/L3.

## Unsafe control actions on the two decisions

The cache exposes exactly two control actions. `requires_full_pass` decides whether the
whole stored pass is discarded; `detect_changed_paths` decides which individual files are
recomputed. For each, the four STPA forms:

| # | Control action | Unsafe form | Hazard |
|---|---|---|---|
| U1 | reuse whole pass | provided when the engine changed | H2 |
| U2 | reuse whole pass | provided when the scope differs | H5 |
| U3 | reuse whole pass | provided when there is no/foreign state | H3, H6 |
| U4 | reuse whole pass | *not* provided though nothing relevant changed (a commit) | H4 |
| U5 | mark file changed | not provided though content changed | H1 |
| U6 | mark file changed | not provided because only metadata was compared | H1 |
| U7 | mark file changed | provided though content is identical | H4 |
| U8 | report deletion | not provided when a file disappeared | H5 |

## Severity / occurrence / detectability

Scored on the project's anchored scales (S: 9–10 = user confidently acts on a wrong
answer; O: exposure of the triggering situation; D: 9–10 = nothing distinguishes wrong
from right).

| UCA | S | O | D | Why it is rated there |
|---|---|---|---|---|
| U5/U6 | 10 | 5 | 10 | A stale clean report is indistinguishable from a healthy one.
  Same-length edits are ordinary: a status flip, an id swap, a tool rewrite. |
| U1 | 10 | 5 | 10 | Every verifier upgrade is an occurrence, and a newly added rule
  stays invisible with no signal at all. |
| U3 | 9 | 3 | 9 | Reading v1 snapshots as v2 compares absent keys, so *every* file reads
  as unchanged — a whole-repository silent clean pass. |
| U8 | 7 | 5 | 6 | Results for a vanished file linger; noticed only if someone reconciles
  counts. |
| U4 | 3 | 9 | 1 | Pure cost, plainly visible. Highest occurrence of all — it fired on
  every commit — hence worth fixing despite low severity. |
| U7 | 3 | 3 | 1 | Pure cost, visible. |

Detectability is the reason this file is dense: for the high-severity rows, nothing in
the product's own output distinguishes the failure from success, so a test is the only
detection mechanism that exists.

## What is deliberately not covered here

Concurrent verification of one repository by two processes, and the durability of the
state file under power loss. Both are real, neither is decided by this module: the state
is written through a temporary file and an atomic replace, and a lost or torn state falls
back to a full pass, which is safe in the L1 direction.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.application.verification._verifier_inventory import FileInventory, content_hash
from src.application.verification.artifact_verifier_incremental import (
    STATE_SCHEMA_VERSION,
    detect_changed_paths,
    load_incremental_state,
    requires_full_pass,
    save_incremental_state,
)
from src.application.verification.artifact_verifier_types import IncrementalState


def _inventory(repo: Path, *files: Path) -> FileInventory:
    inv = FileInventory(repo_path=repo)
    for f in files:
        inv.add_file(f, "entity")
    return inv


def _state(inv: FileInventory, *, head: str | None = "abc123", sig: str = "sig",
           include_diagrams: bool = True, include_registry: bool = False) -> IncrementalState:
    return IncrementalState(
        schema_version=STATE_SCHEMA_VERSION,
        engine_signature=sig,
        include_diagrams=include_diagrams,
        git_head=head,
        snapshots=inv.snapshots,
        results={},
        include_registry=include_registry,
    )


# ---------------------------------------------------------------------------
# U5 / U6 — a changed file must never keep a cached result. Highest severity.
# ---------------------------------------------------------------------------


class TestAChangedFileIsAlwaysRecomputed:
    """The problem dimension is *how* content changed and what the metadata did meanwhile.
    Each case below is a different combination, because the previous keying passed some of
    them and silently failed others."""

    @pytest.mark.parametrize(
        "before_text, after_text, label",
        [
            ("aaaa", "bbbb", "same length, different bytes"),
            ("aaaa", "aaaaa", "longer"),
            ("aaaaa", "aaaa", "shorter"),
            ("", "x", "empty to non-empty"),
            ("x", "", "non-empty to empty"),
            ("line\n", "line\r\n", "line ending only"),
            ("a b", "a  b", "whitespace only"),
            ("café", "cafe", "non-ascii to ascii, same visual length"),
            ("aaaa", "aaab", "single byte at the end"),
            ("aaaa", "baaa", "single byte at the start"),
        ],
    )
    def test_content_change_is_detected_whatever_the_mtime_says(
        self, tmp_path: Path, before_text: str, after_text: str, label: str
    ) -> None:
        f = tmp_path / "a.md"
        f.write_text(before_text, encoding="utf-8")
        before = _state(_inventory(tmp_path, f))
        stat = f.stat()

        f.write_text(after_text, encoding="utf-8")
        # Restore the *old* metadata: the adversarial case for any mtime-based scheme.
        os.utime(f, ns=(stat.st_atime_ns, stat.st_mtime_ns))

        changed, _ = detect_changed_paths(_inventory(tmp_path, f), before)
        assert changed == {"a.md"}, f"undetected change ({label}) — a stale clean report"

    def test_a_same_length_edit_with_identical_mtime_is_detected(self, tmp_path: Path) -> None:
        """U6 stated at its sharpest: every metadata signal the old scheme compared is
        identical, so only content can distinguish these two files."""
        f = tmp_path / "a.md"
        f.write_text("status: draft")
        before = _state(_inventory(tmp_path, f))
        stat = f.stat()

        f.write_text("status: final")  # identical byte length
        os.utime(f, ns=(stat.st_atime_ns, stat.st_mtime_ns))

        assert f.stat().st_size == stat.st_size
        assert f.stat().st_mtime_ns == stat.st_mtime_ns
        changed, _ = detect_changed_paths(_inventory(tmp_path, f), before)
        assert changed == {"a.md"}

    def test_binary_content_is_hashed_not_decoded(self, tmp_path: Path) -> None:
        """Hashing must not assume text: a diagram or an attachment that is not valid UTF-8
        must be comparable rather than raise, or the pass dies on an unrelated file."""
        f = tmp_path / "a.md"
        f.write_bytes(b"\xff\xfe\x00binary")
        before = _state(_inventory(tmp_path, f))
        f.write_bytes(b"\xff\xfe\x00binaryX")
        changed, _ = detect_changed_paths(_inventory(tmp_path, f), before)
        assert changed == {"a.md"}

    def test_a_file_larger_than_one_read_chunk_is_hashed_whole(self, tmp_path: Path) -> None:
        """The hash reads in chunks; a change past the first chunk must still register, or
        large diagrams would be effectively unverified."""
        f = tmp_path / "a.md"
        f.write_text("x" * 300_000)
        before = _state(_inventory(tmp_path, f))
        f.write_text("x" * 299_999 + "y")  # differs only in the final byte
        changed, _ = detect_changed_paths(_inventory(tmp_path, f), before)
        assert changed == {"a.md"}


# ---------------------------------------------------------------------------
# U7 — an unchanged file must keep its result, however its metadata was rewritten.
# ---------------------------------------------------------------------------


class TestAnUnchangedFileKeepsItsResult:
    @pytest.mark.parametrize(
        "rewrite, label",
        [
            (lambda f: os.utime(f, (1, 1)), "mtime rewound (checkout, restore)"),
            (lambda f: os.utime(f, None), "mtime advanced to now (clone, cp)"),
            (lambda f: f.write_text(f.read_text()), "rewritten with identical bytes"),
        ],
    )
    def test_metadata_only_rewrites_do_not_invalidate(self, tmp_path: Path, rewrite, label: str) -> None:
        f = tmp_path / "a.md"
        f.write_text("same content")
        before = _state(_inventory(tmp_path, f))

        rewrite(f)

        changed, deleted = detect_changed_paths(_inventory(tmp_path, f), before)
        assert changed == set(), f"needless full pass after {label}"
        assert deleted == set()

    def test_identical_content_at_a_different_path_is_not_confused(self, tmp_path: Path) -> None:
        """Identity is (relpath, content) — two files sharing content are still two files,
        and a rename is an addition plus a deletion, not a no-op."""
        a, b = tmp_path / "a.md", tmp_path / "b.md"
        a.write_text("shared")
        before = _state(_inventory(tmp_path, a))
        b.write_text("shared")
        a.unlink()

        changed, deleted = detect_changed_paths(_inventory(tmp_path, b), before)
        assert changed == {"b.md"} and deleted == {"a.md"}


# ---------------------------------------------------------------------------
# U8 / H5 — the result set must stay in step with the file set.
# ---------------------------------------------------------------------------


class TestAdditionsAndDeletionsAreReported:
    def test_a_new_file_is_reported_changed(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        a.write_text("x")
        before = _state(_inventory(tmp_path, a))
        b = tmp_path / "b.md"
        b.write_text("y")
        changed, deleted = detect_changed_paths(_inventory(tmp_path, a, b), before)
        assert changed == {"b.md"} and deleted == set()

    def test_a_removed_file_is_reported_deleted(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        a.write_text("x")
        before = _state(_inventory(tmp_path, a))
        changed, deleted = detect_changed_paths(FileInventory(repo_path=tmp_path), before)
        assert deleted == {"a.md"} and changed == set()

    def test_an_empty_repository_against_empty_state_is_stable(self, tmp_path: Path) -> None:
        empty = _state(FileInventory(repo_path=tmp_path))
        changed, deleted = detect_changed_paths(FileInventory(repo_path=tmp_path), empty)
        assert changed == set() and deleted == set()


# ---------------------------------------------------------------------------
# U1–U4 — discarding the whole pass. The solution dimension is which inputs may
# legitimately force it.
# ---------------------------------------------------------------------------


class TestWholePassReuseDecision:
    def _prev(self, **kw) -> IncrementalState:
        return _state(FileInventory(repo_path=Path("/nowhere")), **kw)

    def test_unchanged_inputs_reuse_the_pass(self) -> None:
        assert not requires_full_pass(
            self._prev(), include_diagrams=True, engine_sig="sig", has_registry=False
        )

    def test_a_changed_engine_forces_a_full_pass(self) -> None:
        """U1. Without this an upgraded verifier keeps reporting the previous one's
        conclusions and a newly added rule never fires."""
        assert requires_full_pass(
            self._prev(sig="old"), include_diagrams=True, engine_sig="new", has_registry=False
        )

    @pytest.mark.parametrize("stored, asked", [(True, False), (False, True)])
    def test_a_changed_diagram_scope_forces_a_full_pass(self, stored: bool, asked: bool) -> None:
        """U2, both directions: a pass that skipped diagrams cannot answer for them, and a
        pass that included them holds results the narrower question did not ask for."""
        assert requires_full_pass(
            self._prev(include_diagrams=stored), include_diagrams=asked,
            engine_sig="sig", has_registry=False,
        )

    @pytest.mark.parametrize("stored, now", [(True, False), (False, True)])
    def test_a_changed_registry_availability_forces_a_full_pass(self, stored: bool, now: bool) -> None:
        """Registry-dependent rules are skipped without it, so results are not comparable
        across that boundary in either direction."""
        assert requires_full_pass(
            self._prev(include_registry=stored), include_diagrams=True,
            engine_sig="sig", has_registry=now,
        )

    def test_absent_state_forces_a_full_pass(self) -> None:
        assert requires_full_pass(None, include_diagrams=True, engine_sig="sig", has_registry=False)

    @pytest.mark.parametrize("old_head, new_head", [
        ("old-sha", "new-sha"),
        (None, "first-commit"),
        ("sha", None),
    ])
    def test_a_moved_head_alone_does_not_force_a_full_pass(self, old_head, new_head) -> None:
        """U4 — the highest-occurrence unsafe action, and the reason this changed. Every
        `artifact_save_changes` moves HEAD; gating on it re-verified the whole repository
        after every save. It is safe to ignore because nothing in verification reads
        git-committed content, so a commit cannot change a conclusion without changing a
        file — and that file is caught by its hash."""
        assert not requires_full_pass(
            self._prev(head=old_head), include_diagrams=True, engine_sig="sig", has_registry=False
        ), "a commit must not discard cached results"


# ---------------------------------------------------------------------------
# U3 / H3 / H6 — state that must not be trusted.
# ---------------------------------------------------------------------------


class TestUntrustworthyStateIsRejected:
    def test_state_from_the_mtime_keyed_schema_is_discarded_not_reinterpreted(self, tmp_path: Path) -> None:
        """The worst single failure available here. Version 1 snapshots carry mtime_ns and
        size where version 2 carries content_hash; comparing them field-wise finds absent
        keys equal to absent keys, so *every* file reads as unchanged and the whole
        repository is reported clean without one file being verified."""
        legacy = tmp_path / "state.json"
        legacy.write_text(json.dumps({
            "schema_version": 1, "engine_signature": "sig", "include_diagrams": True,
            "git_head": "abc", "snapshots": {"a.md": {"mtime_ns": 1, "size": 4}}, "results": {},
        }))
        assert load_incremental_state(legacy) is None

    def test_the_absent_key_trap_is_real(self, tmp_path: Path) -> None:
        """Demonstrates *why* the version check must reject rather than adapt: if v1
        snapshots were compared directly, a changed file would read as unchanged."""
        f = tmp_path / "a.md"
        f.write_text("new content")
        v1_style = IncrementalState(
            schema_version=STATE_SCHEMA_VERSION, engine_signature="sig", include_diagrams=True,
            git_head=None, snapshots={"a.md": {"mtime_ns": 1, "size": 4}}, results={},
        )
        changed, _ = detect_changed_paths(_inventory(tmp_path, f), v1_style)
        assert changed == {"a.md"}, (
            "comparing a hash against an absent key must not read as unchanged; if this "
            "ever fails, the schema-version rejection is the only thing preventing a "
            "silent clean pass over an entire repository"
        )

    @pytest.mark.parametrize("payload, label", [
        ("{ not json", "truncated"),
        ("[]", "not an object"),
        ('{"schema_version": 2, "snapshots": [], "results": {}}', "snapshots wrong type"),
        ('{"schema_version": 2, "snapshots": {}, "results": []}', "results wrong type"),
        ('{"schema_version": 99, "snapshots": {}, "results": {}}', "future schema"),
    ])
    def test_unreadable_state_is_rejected_outright(self, tmp_path: Path, payload: str, label: str) -> None:
        """H6. Rejection returns None, which the caller reads as 'no usable state' and
        answers with a full pass — slow, never silently stale."""
        state = tmp_path / "state.json"
        state.write_text(payload)
        assert load_incremental_state(state) is None, f"accepted {label} state"

    @pytest.mark.parametrize("payload, label", [
        ('{"schema_version": 2}', "header only, no snapshots or results"),
        ('{"schema_version": 2, "snapshots": {}, "results": {}, "engine_signature": "sig"}',
         "plausible header, empty inventory"),
    ])
    def test_degenerate_state_cannot_produce_a_stale_clean_pass(
        self, tmp_path: Path, payload: str, label: str
    ) -> None:
        """Some degenerate documents parse rather than being rejected, and that is
        acceptable — but only if they cannot cause stale reuse. The property under test is
        the hazard (H6), not the mechanism: whatever such a state is, either it is refused,
        or it forces a full pass, or every real file still reads as changed. Asserting
        `is None` here would have tested an implementation choice and missed the point."""
        f = tmp_path / "a.md"
        f.write_text("real content")
        state = tmp_path / "state.json"
        state.write_text(payload)

        loaded = load_incremental_state(state)
        if loaded is None:
            return  # refused outright — safe
        forces_full = requires_full_pass(
            loaded, include_diagrams=True, engine_sig="the-real-engine-signature", has_registry=False
        )
        changed, _ = detect_changed_paths(_inventory(tmp_path, f), loaded)
        assert forces_full or changed == {"a.md"}, (
            f"{label}: parsed into a state that would reuse results for a file it has "
            "never seen — a clean report over an unverified repository"
        )

    def test_a_missing_state_file_is_not_an_error(self, tmp_path: Path) -> None:
        assert load_incremental_state(tmp_path / "absent.json") is None


# ---------------------------------------------------------------------------
# Round-trip consistency: what is written must be what is read.
# ---------------------------------------------------------------------------


class TestStateRoundTrip:
    def test_a_saved_state_reloads_with_its_snapshots_and_flags_intact(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("x")
        original = _state(_inventory(tmp_path, f), head="sha", sig="sig-1", include_registry=True)
        path = tmp_path / "state.json"
        save_incremental_state(path, original)

        loaded = load_incremental_state(path)
        assert loaded is not None
        assert loaded.snapshots == original.snapshots
        assert loaded.engine_signature == original.engine_signature
        assert loaded.include_diagrams == original.include_diagrams
        assert loaded.include_registry == original.include_registry
        assert loaded.git_head == original.git_head

    def test_a_reloaded_state_reuses_the_pass_it_was_written_from(self, tmp_path: Path) -> None:
        """The end-to-end consistency criterion: save then load must not, by itself, change
        any reuse decision."""
        f = tmp_path / "a.md"
        f.write_text("x")
        inv = _inventory(tmp_path, f)
        path = tmp_path / "state.json"
        save_incremental_state(path, _state(inv, sig="sig"))

        loaded = load_incremental_state(path)
        assert loaded is not None
        assert not requires_full_pass(
            loaded, include_diagrams=True, engine_sig="sig", has_registry=False
        )
        assert detect_changed_paths(_inventory(tmp_path, f), loaded) == (set(), set())

    def test_saving_never_leaves_a_partial_file_in_place(self, tmp_path: Path) -> None:
        """State is written to a temporary file and moved into place, so a reader never
        observes a half-written document."""
        f = tmp_path / "a.md"
        f.write_text("x")
        path = tmp_path / "state.json"
        save_incremental_state(path, _state(_inventory(tmp_path, f)))
        assert load_incremental_state(path) is not None
        assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# The hash itself.
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_identical_content_hashes_identically_at_different_paths(self, tmp_path: Path) -> None:
        a, b = tmp_path / "a.md", tmp_path / "b.md"
        a.write_text("same")
        b.write_text("same")
        assert content_hash(a) == content_hash(b)

    def test_the_snapshot_records_that_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("payload")
        assert _inventory(tmp_path, f).snapshots["a.md"]["content_hash"] == content_hash(f)

    def test_hashing_is_stable_across_repeated_reads(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text("payload")
        assert content_hash(f) == content_hash(f)
