"""Where the installed tree is rooted, for the commands that provision into it.

A provisioning command and whatever later looks for what it installed must agree on one directory,
or the command reports success over a file nothing can find. The agreement is this function plus a
relative path constant per asset, never a path spelled twice.
"""

from __future__ import annotations

from pathlib import Path

#: How far above this module the root can be before the search is a bug rather than a deep tree.
_SEARCH_DEPTH = 6


def project_directory() -> Path:
    """The directory holding `pyproject.toml`, which is what every asset path is relative to."""
    candidate = Path(__file__).resolve()
    for _ in range(_SEARCH_DEPTH):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise SystemExit("Could not locate the project directory (no pyproject.toml above this module)")
