"""``RepoExchangeIdentityStore`` (WU-F3a): JSON sidecar persistence + gitignore hygiene."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.exchange.archimate_model_exchange.identity_store import RepoExchangeIdentityStore


def test_unknown_exchange_id_returns_none(tmp_path: Path) -> None:
    store = RepoExchangeIdentityStore(tmp_path)
    assert store.artifact_id_for("exchange-1") is None


def test_record_then_lookup_round_trips(tmp_path: Path) -> None:
    store = RepoExchangeIdentityStore(tmp_path)
    store.record("exchange-1", "BOB@123.abc.foo")
    assert store.artifact_id_for("exchange-1") == "BOB@123.abc.foo"


def test_record_persists_across_new_instances(tmp_path: Path) -> None:
    RepoExchangeIdentityStore(tmp_path).record("exchange-1", "BOB@123.abc.foo")
    reloaded = RepoExchangeIdentityStore(tmp_path)
    assert reloaded.artifact_id_for("exchange-1") == "BOB@123.abc.foo"


def test_record_adds_gitignore_entry(tmp_path: Path) -> None:
    RepoExchangeIdentityStore(tmp_path).record("exchange-1", "BOB@123.abc.foo")
    gitignore = tmp_path / ".arch-repo" / ".gitignore"
    assert "exchange-identity.json" in gitignore.read_text(encoding="utf-8").splitlines()


def test_record_does_not_duplicate_gitignore_entry(tmp_path: Path) -> None:
    store = RepoExchangeIdentityStore(tmp_path)
    store.record("exchange-1", "BOB@123.abc.foo")
    store.record("exchange-2", "BOB@124.abc.bar")
    gitignore = tmp_path / ".arch-repo" / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count("exchange-identity.json") == 1
