"""A staged batch publishes every change it made, or it publishes nothing.

The commit manifest is derived from the paths the writes reported touching, and only the managed
subtrees can appear in it. A touched path outside them was dropped here without a word — and by then
the write had already happened in the staged root, had already answered `wrote: true`, and the batch
verification had already passed. The change simply never reached the live repository.

That is the one outcome a transaction must never produce: a partial commit that reports success. No
operation reaches it today, since bulk write and bulk delete are the only users of the staged
transaction and every path they touch is under a managed subtree — which is exactly why it was worth
closing before something does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.batch_transaction import (
    UnrepresentableChangeError,
    _derive_manifest_from_touched_paths,
)


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    live, staged = tmp_path / "live", tmp_path / "staged"
    for root in (live, staged):
        for subtree in ("model", "scratchpads", ".arch-repo"):
            (root / subtree).mkdir(parents=True)
    return live, staged


def _change(live: Path, staged: Path, relpath: str) -> Path:
    (live / relpath).write_text("before", encoding="utf-8")
    (staged / relpath).write_text("after", encoding="utf-8")
    return (staged / relpath).resolve()


def test_a_managed_change_is_carried(roots: tuple[Path, Path]) -> None:
    live, staged = roots
    touched = {_change(live, staged, "model/a.md")}

    entries, result = _derive_manifest_from_touched_paths(
        live_root=live, staged_root=staged, touched_paths=touched
    )

    assert [(entry.kind, entry.dest) for entry in entries] == [("replace", "model/a.md")]
    assert result.changed_paths == [live / "model" / "a.md"]


@pytest.mark.parametrize("relpath", ["scratchpads/p.scratchpad.yaml", ".arch-repo/groups.yaml"])
def test_a_change_the_manifest_cannot_carry_stops_the_commit(
    roots: tuple[Path, Path], relpath: str
) -> None:
    live, staged = roots
    touched = {_change(live, staged, relpath)}

    with pytest.raises(UnrepresentableChangeError, match=relpath.split("/")[0]):
        _derive_manifest_from_touched_paths(
            live_root=live, staged_root=staged, touched_paths=touched
        )


def test_one_unrepresentable_change_stops_the_whole_batch(roots: tuple[Path, Path]) -> None:
    """Not "commit what we can": a batch that published its managed half and dropped the rest would
    be the silent partial commit under another name."""
    live, staged = roots
    touched = {
        _change(live, staged, "model/a.md"),
        _change(live, staged, "scratchpads/p.scratchpad.yaml"),
    }

    with pytest.raises(UnrepresentableChangeError) as raised:
        _derive_manifest_from_touched_paths(
            live_root=live, staged_root=staged, touched_paths=touched
        )

    assert "scratchpads" in str(raised.value)
    assert (live / "model" / "a.md").read_text(encoding="utf-8") == "before", "nothing was published"


def test_a_deletion_is_carried_like_a_rewrite(roots: tuple[Path, Path]) -> None:
    """A delete removes the staged file, so the manifest has to read its absence as a change rather
    than as nothing to do."""
    live, staged = roots
    (live / "model" / "gone.md").write_text("here", encoding="utf-8")
    touched = {(staged / "model" / "gone.md").resolve()}

    entries, result = _derive_manifest_from_touched_paths(
        live_root=live, staged_root=staged, touched_paths=touched
    )

    assert [(entry.kind, entry.dest) for entry in entries] == [("delete", "model/gone.md")]
    assert result.deleted_paths == [live / "model" / "gone.md"]
