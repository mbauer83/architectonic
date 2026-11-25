"""When the assurance module is absent from a running backend, the refusal says why and what to do.

Following the installation guide in order — start the backend, then `arch-assurance init` and
`unlock` — left the store unlocked but the module unregistered, because modules register once, at
startup. `GET /api/assurance/edge-catalog` then answered "Enable the assurance module in
config/settings.yaml", which was not the cause. The remedy is now derived from the cause, and `init`
says a restart is needed when a backend is already running.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure import app_bootstrap


def _capability(monkeypatch: pytest.MonkeyPatch, *, enabled: bool, overrides: dict[str, dict[str, object]]) -> None:
    import src.config.settings as settings

    monkeypatch.setattr(app_bootstrap, "capability_for_deployment", lambda: SimpleNamespace(enabled=enabled))
    monkeypatch.setattr(settings, "module_overrides", lambda: overrides)


def test_a_store_that_arrived_after_startup_asks_for_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    _capability(monkeypatch, enabled=True, overrides={})

    remedy = app_bootstrap.assurance_module_absence_remedy()

    assert "arch-backend --restart --daemon" in remedy
    assert "config/settings.yaml" not in remedy


def test_no_readable_store_asks_for_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _capability(monkeypatch, enabled=False, overrides={})

    assert "arch-assurance init" in app_bootstrap.assurance_module_absence_remedy()


def test_a_disabled_module_names_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    _capability(monkeypatch, enabled=True, overrides={"assurance": {"enabled": False}})

    assert "modules.assurance.enabled" in app_bootstrap.assurance_module_absence_remedy()


def test_the_edge_catalog_refusal_carries_the_derived_remedy(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.rest.contracts.errors import ApiError
    from src.infrastructure.rest.routers.assurance import router

    monkeypatch.setattr(router, "get_module_registry", lambda: SimpleNamespace(find_ontology=lambda _n: None))
    monkeypatch.setattr(router, "assurance_module_absence_remedy", lambda: "restart it")

    with pytest.raises(ApiError) as raised:
        router.assurance_edge_catalog()

    assert "restart it" in str(raised.value.details)


def test_init_with_a_backend_running_says_to_restart_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    import src.infrastructure.assurance.lifecycle as lifecycle
    from src.infrastructure.cli import _assurance_commands as commands

    monkeypatch.setattr(lifecycle, "init_store", lambda db_path, force=False: {"status": "initialised"})
    monkeypatch.setattr(commands, "write_storage_config", lambda *_a, **_k: None)
    monkeypatch.setattr(commands, "_running_backend_url", lambda: "http://127.0.0.1:1")

    status = commands.cmd_init(argparse.Namespace(db_path=str(tmp_path / "store.db"), force=False))

    assert status == 0
    assert "arch-backend --restart --daemon" in capsys.readouterr().out
