"""`uv sync` with no group installs everything `arch-backend` imports.

The installation guide's first command is a plain `uv sync`. The web stack used to live only in the
`gui` dependency group, so after that command `arch-backend` — and every MCP stdio bridge, which starts
it — died with `ModuleNotFoundError: No module named 'fastapi'`, even for `--help`.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: The distributions the backend's import graph needs beyond the standard library's reach, by the
#: module that fails first without them.
_BACKEND_WEB_STACK = ("fastapi", "uvicorn")


def _names(requirements: list[str]) -> set[str]:
    return {re.split(r"[\s\[<>=!~;]", item, maxsplit=1)[0].lower() for item in requirements}


def test_the_web_stack_is_a_core_dependency() -> None:
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    core = _names(project["project"]["dependencies"])
    missing = [name for name in _BACKEND_WEB_STACK if name not in core]
    assert not missing, f"arch-backend imports {missing}, which a plain `uv sync` would not install"


def test_the_gui_group_still_exists_for_commands_that_name_it_and_declares_nothing() -> None:
    # Installations from before the web stack was core, and commands written for them, pass
    # `--group gui`; uv refuses an unknown group, so the group stays. It is empty: a second
    # declaration of the web stack's version floor would drift from the core one.
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert project["dependency-groups"]["gui"] == []
