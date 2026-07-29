"""`write_storage_config` does not rewrite a settings document it does not change.

`arch-assurance init` re-asserts `storage.assurance.store_backend` and `signals_backend` on
every run, and those are normally already the configured values. Writing regardless would
round-trip the whole document through PyYAML, which cannot preserve comments — so a first
`arch-assurance init` on a fresh clone would delete the explanatory prose shipped in
`config/settings.yaml`, and reorder its keys, while changing no setting at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.infrastructure.cli._config_helpers import write_storage_config

_COMMENTED = """\
backend:
  port: 8000
storage:
  assurance:
    # Which encrypted backend holds the confidential store.
    store_backend: sqlcipher
    signals_backend: sqlcipher-colocated
repo_init:
  # Placeholder identity — set this to your own.
  commit_author_name: Architecture Bot
  commit_author_email: architecture-bot@example.com
"""


@pytest.fixture()
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(_COMMENTED, encoding="utf-8")
    monkeypatch.setenv("ARCH_SETTINGS_PATH", str(path))
    return path


def test_no_op_write_leaves_the_document_byte_for_byte(settings_file: Path) -> None:
    write_storage_config("sqlcipher", "sqlcipher-colocated")

    assert settings_file.read_text(encoding="utf-8") == _COMMENTED


def test_comments_survive_a_run_that_changes_nothing(settings_file: Path) -> None:
    write_storage_config("sqlcipher", "sqlcipher-colocated")

    text = settings_file.read_text(encoding="utf-8")
    assert "# Placeholder identity — set this to your own." in text
    assert "# Which encrypted backend holds the confidential store." in text


def test_a_real_change_is_still_written(settings_file: Path) -> None:
    write_storage_config("sqlcipher", "sqlcipher-colocated", activation_policy="persistent")

    written = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    assurance = written["storage"]["assurance"]
    assert assurance["activation_policy"] == "persistent"
    assert assurance["store_backend"] == "sqlcipher"
    assert assurance["signals_backend"] == "sqlcipher-colocated"
    # Unrelated settings must survive the rewrite even though its comments cannot.
    assert written["repo_init"]["commit_author_name"] == "Architecture Bot"
    assert written["backend"]["port"] == 8000


def test_backend_switch_is_written(settings_file: Path) -> None:
    write_storage_config("pocketbase", "pocketbase")

    assurance = yaml.safe_load(settings_file.read_text(encoding="utf-8"))["storage"]["assurance"]
    assert assurance == {"store_backend": "pocketbase", "signals_backend": "pocketbase"}


def test_creates_the_document_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "nested" / "settings.yaml"
    path.parent.mkdir()
    monkeypatch.setenv("ARCH_SETTINGS_PATH", str(path))

    write_storage_config("sqlcipher", "sqlcipher-colocated")

    assurance = yaml.safe_load(path.read_text(encoding="utf-8"))["storage"]["assurance"]
    assert assurance == {"store_backend": "sqlcipher", "signals_backend": "sqlcipher-colocated"}
