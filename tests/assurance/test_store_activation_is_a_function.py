"""Activating the store is one function, not the body of a CLI handler.

The updater has to re-authorize the store after it restarts a backend under the `manual` policy, and
the only way to do that used to be `arch-assurance unlock` as a subprocess or a copy of its body. The
ceremony — open with the key on record, read the statistics, lock, write the activation gate, tell
the running backend — now has one owner, and a failed open records nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.assurance import _credential_accounts as accounts
from src.infrastructure.assurance import activation


class _Store:
    instances: list["_Store"] = []

    def __init__(self, db_path: Path, *, opens: bool = True) -> None:
        self.db_path = db_path
        self.opens = opens
        self.events: list[str] = []
        _Store.instances.append(self)

    def unlock(self) -> None:
        if not self.opens:
            raise RuntimeError("no key")
        self.events.append("unlock")

    def stats(self) -> dict[str, int]:
        self.events.append("stats")
        return {"nodes": 3}

    def lock(self) -> None:
        self.events.append("lock")


@pytest.fixture()
def gate(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    written: dict[str, str] = {}
    monkeypatch.setattr(accounts, "write", lambda base, store_path, value: written.__setitem__(base, value))
    monkeypatch.setattr(accounts, "clear", lambda base, store_path: written.pop(base, None))
    return written


@pytest.fixture()
def reloads(monkeypatch: pytest.MonkeyPatch) -> list[bool | None]:
    seen: list[bool | None] = []
    monkeypatch.setattr(activation, "notify_backend_reload", lambda *, authorize=None: seen.append(authorize))
    return seen


def _stores(monkeypatch: pytest.MonkeyPatch, *, opens: bool) -> None:
    import src.infrastructure.assurance._sqlcipher_store as module

    _Store.instances.clear()
    monkeypatch.setattr(module, "SQLCipherAssuranceStore", lambda db_path: _Store(db_path, opens=opens))


def test_activation_opens_reads_locks_records_and_authorizes(monkeypatch, gate, reloads, tmp_path) -> None:  # noqa: ANN001
    _stores(monkeypatch, opens=True)

    result = activation.activate_store(tmp_path / "store.db")

    assert result.stats == {"nodes": 3}
    assert _Store.instances[0].events == ["unlock", "stats", "lock"]
    assert gate == {accounts.SETUP_GATE: "1"}
    assert reloads == [True]


def test_a_store_that_will_not_open_records_nothing(monkeypatch, gate, reloads, tmp_path) -> None:  # noqa: ANN001
    _stores(monkeypatch, opens=False)

    with pytest.raises(RuntimeError):
        activation.activate_store(tmp_path / "store.db")

    assert gate == {}
    assert reloads == []


def test_deactivation_clears_the_gate_and_revokes_on_the_running_backend(gate, reloads, tmp_path) -> None:  # noqa: ANN001
    gate[accounts.SETUP_GATE] = "1"

    activation.deactivate_store(tmp_path / "store.db")

    assert gate == {}
    assert reloads == [False]
