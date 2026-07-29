"""Atomic write + stray-tmp-file resilience for the D17 filesystem writer."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.atomic_file import sweep_stale_tmp_files, write_atomic


def test_write_atomic_leaves_no_tmp_file_on_success(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "file.txt"
    write_atomic(target, "content")

    assert target.read_text(encoding="utf-8") == "content"
    assert list(tmp_path.rglob("*.tmp-*")) == []


def test_write_atomic_never_leaves_partial_content_if_interrupted_before_replace(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("original", encoding="utf-8")
    # Simulate a crash between the temp-file write and the rename: only the tmp file exists.
    tmp_path_orphan = target.with_name(f".{target.name}.tmp-99999")
    tmp_path_orphan.write_text("half-written", encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "original"

    removed = sweep_stale_tmp_files(tmp_path)

    assert removed == [tmp_path_orphan.name]
    assert not tmp_path_orphan.exists()
    assert target.read_text(encoding="utf-8") == "original"


def test_sweep_is_a_no_op_when_nothing_stale(tmp_path: Path) -> None:
    (tmp_path / "normal.txt").write_text("x", encoding="utf-8")
    assert sweep_stale_tmp_files(tmp_path) == []
