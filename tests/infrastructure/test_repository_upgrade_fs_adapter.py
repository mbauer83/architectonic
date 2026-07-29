"""Tests for FilesystemRepoUpgradeView.read_text's robustness against unreadable/non-UTF-8
content — a step scanning `**/*.puml`/`**/*.md` broadly must not crash its whole detect()
pass over one corrupted or unexpectedly-binary file."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView


def test_read_text_returns_none_for_non_utf8_content(tmp_path: Path) -> None:
    (tmp_path / "corrupt.md").write_bytes(b"\xff\xfe\x00---not valid utf-8\x80\x81")

    assert FilesystemRepoUpgradeView(tmp_path).read_text("corrupt.md") is None


def test_read_text_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert FilesystemRepoUpgradeView(tmp_path).read_text("missing.md") is None


def test_read_text_returns_content_for_normal_file(tmp_path: Path) -> None:
    (tmp_path / "ok.md").write_text("hello", encoding="utf-8")

    assert FilesystemRepoUpgradeView(tmp_path).read_text("ok.md") == "hello"
