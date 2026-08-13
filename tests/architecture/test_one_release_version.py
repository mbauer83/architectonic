"""A release is one version, and every file that states it says the same thing.

The version is written down five times — `pyproject.toml`, `uv.lock`'s entry for this project,
`tools/gui/package.json`, and **twice** inside `tools/gui/package-lock.json`, which records it at
the top level and again under `packages[""]`. Every release has bumped them by hand, and the
lockfile's second copy is the one a person editing the first does not think about.

Nothing failed when they disagreed. The backend answers `/api/backend-identity` from
`pyproject.toml` while the built SPA carries `package.json`'s, so a mismatch ships as two different
version numbers in one product, discovered by whoever is trying to work out which build they have.

Stated as "they agree" rather than "they equal `X`": the release version is whatever the project
says it is, and a gate naming a literal is a gate that fails on the bump it exists to protect.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _ROOT / "pyproject.toml"
_UV_LOCK = _ROOT / "uv.lock"
_PACKAGE_JSON = _ROOT / "tools" / "gui" / "package.json"
_PACKAGE_LOCK = _ROOT / "tools" / "gui" / "package-lock.json"


def _pyproject_version() -> str:
    return str(tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])


def _uv_lock_version(project_name: str) -> str | None:
    """The version `uv.lock` records for this project itself, or None if it names none.

    Read as text rather than by parsing the whole lock: the file is TOML, but its shape is uv's and
    tying a gate to it would make a uv upgrade a test failure. The project's own block is the one
    stanza whose `name` is this project.
    """
    match = re.search(
        rf'^\[\[package\]\]\nname = "{re.escape(project_name)}"\nversion = "([^"]+)"',
        _UV_LOCK.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _stated_versions() -> dict[str, str]:
    """Every place the release version is written down, by the name a person would look under."""
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    lock = json.loads(_PACKAGE_LOCK.read_text(encoding="utf-8"))
    stated = {
        "pyproject.toml [project.version]": str(project["version"]),
        "tools/gui/package.json": str(json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))["version"]),
        "tools/gui/package-lock.json .version": str(lock["version"]),
        'tools/gui/package-lock.json .packages[""].version': str(lock["packages"][""]["version"]),
    }
    uv_version = _uv_lock_version(str(project["name"]))
    if uv_version is not None:
        stated["uv.lock [[package]] for this project"] = uv_version
    return stated


def test_every_file_that_states_the_release_version_states_the_same_one() -> None:
    stated = _stated_versions()
    distinct = sorted(set(stated.values()))

    assert len(distinct) == 1, (
        "the release version disagrees across the files that record it — bump them together:\n"
        + "\n".join(f"  {where}: {version}" for where, version in sorted(stated.items()))
    )


def test_the_walk_reaches_every_file_it_claims_to() -> None:
    """A guard on the guard: were a path to move, the comparison above would quietly shrink to the
    files that remain and keep passing."""
    for path in (_PYPROJECT, _UV_LOCK, _PACKAGE_JSON, _PACKAGE_LOCK):
        assert path.is_file(), f"{path} is not where this gate looks for it"
    assert len(_stated_versions()) >= 4


@pytest.mark.parametrize("version", [_pyproject_version()])
def test_the_version_is_a_release_number_rather_than_a_placeholder(version: str) -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{version!r} is not a release number"
