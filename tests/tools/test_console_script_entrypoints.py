"""Every ``[project.scripts]`` target must resolve to a callable that exists.

Nothing in the suite imports a console script's target: the shim in ``.venv/bin`` is written at
install time from the string in ``pyproject.toml``, and a module rename leaves that string pointing
at nothing. ``arch-gui-server`` shipped in 0.2.0 naming ``src.infrastructure.gui.gui_server`` months
after that package became ``src.infrastructure.rest`` — every gate was green and the command raised
``ModuleNotFoundError`` on ``--help``.

This is the guard for that class. It resolves the manifest, not the installed shim, so it fails in
the same commit as the rename rather than after the next ``uv sync``.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _console_scripts() -> dict[str, str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return project["project"]["scripts"]


@pytest.mark.parametrize(("command", "target"), sorted(_console_scripts().items()))
def test_console_script_target_resolves_to_a_callable(command: str, target: str) -> None:
    module_path, _, attribute = target.partition(":")
    assert attribute, f"{command} = {target!r} names no attribute after ':'"

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:  # pragma: no cover - the failure this test exists for
        pytest.fail(f"{command} = {target!r}: {exc}")

    entry = getattr(module, attribute, None)
    assert entry is not None, f"{command} = {target!r}: {module_path} has no attribute {attribute!r}"
    assert callable(entry), f"{command} = {target!r}: {attribute!r} is not callable"


def test_the_retired_gui_server_alias_is_not_reintroduced() -> None:
    """``src/infrastructure/gui`` is ``src/infrastructure/rest`` since 0.2.0.

    The alias was vestigial — nothing in the repository referenced it and ``arch-backend`` is the
    documented way to run the server — so it was removed rather than repointed. A command named for
    a layer that no longer exists should not come back.
    """
    assert "arch-gui-server" not in _console_scripts()
