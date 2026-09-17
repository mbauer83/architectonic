"""Which dependency groups and extras this environment has, derived so `uv sync` reproduces it.

Nothing records what `uv sync` was run with. A group or extra counts as selected when every
distribution it names is installed; the resulting environment is identical whether or not a subset
group (`s3-archive` inside `dev`) is named, which is the property that matters.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterable
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from src.application.software_update.installation import DependencySelection
from src.infrastructure.software_update._commands import run_checked

_SYNC_TIMEOUT_SECONDS = 1800

#: A requirement's distribution name: what precedes any extras, specifier or marker.
_DISTRIBUTION_NAME = re.compile(r"\A\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def is_installed(distribution_name: str) -> bool:
    try:
        distribution(distribution_name)
    except PackageNotFoundError:
        return False
    return True


def derive_selection(pyproject: Path, *, installed: Callable[[str], bool] = is_installed) -> DependencySelection:
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    groups = project.get("dependency-groups", {})
    extras = project.get("project", {}).get("optional-dependencies", {})
    return DependencySelection(
        groups=tuple(name for name, items in groups.items() if _all_installed(items, installed)),
        extras=tuple(name for name, items in extras.items() if _all_installed(items, installed)),
    )


def _all_installed(requirements: Iterable[object], installed: Callable[[str], bool]) -> bool:
    names = [_name_of(item) for item in requirements if isinstance(item, str)]
    return bool(names) and all(installed(name) for name in names)


def _name_of(requirement: str) -> str:
    match = _DISTRIBUTION_NAME.match(requirement)
    return match.group(1) if match else requirement


def sync(root: Path, selection: DependencySelection, *, uv: str = "uv") -> None:
    """`uv sync --frozen` with the derived selection, in the checkout."""
    command = [uv, "sync", *selection.sync_arguments()]
    run_checked(command, cwd=root, timeout=_SYNC_TIMEOUT_SECONDS, doing=" ".join(command))
