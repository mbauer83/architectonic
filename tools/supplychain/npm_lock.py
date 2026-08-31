#!/usr/bin/env python
"""Read `tools/gui/package-lock.json` into the entries the release-age policy judges.

Unlike `uv.lock`, an npm lockfile records no publish times, so a registry pin's age comes from
`npm_release_evidence`. Everything else about the classification is read from the lock: what a pin
resolved to says which of the four source shapes it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.supplychain.npm_release_evidence import PublishTimes
from tools.supplychain.release_age import (
    ArchiveUrl,
    LocalPath,
    LockedPackage,
    RegistryArtifacts,
    Source,
    vcs_ref,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "tools" / "gui" / "package-lock.json"

_REGISTRY_PREFIX = "https://registry.npmjs.org/"
_NESTING = "node_modules/"


def locked_packages(times: PublishTimes, lock: Path = LOCK) -> tuple[LockedPackage, ...]:
    """Every installed entry of the lock. The root entry is the project itself and is not a pin."""
    document = json.loads(lock.read_text(encoding="utf-8"))
    return tuple(
        LockedPackage(name=_name_of(location), version=str(node.get("version", "")),
                      source=_source_of(_name_of(location), node, times))
        for location, node in document.get("packages", {}).items()
        if location and not node.get("link")
    )


def _name_of(location: str) -> str:
    """`node_modules/a/node_modules/@scope/b` names `@scope/b` — the innermost path segment pair."""
    _, _, innermost = location.rpartition(_NESTING)
    return innermost


def _source_of(name: str, node: dict[str, Any], times: PublishTimes) -> Source:
    resolved = str(node.get("resolved", ""))
    version = str(node.get("version", ""))
    if resolved.startswith(_REGISTRY_PREFIX):
        return RegistryArtifacts(uploaded=(times.of(name, version),))
    if resolved.startswith(("git+", "git:")):
        return vcs_ref(resolved)
    if resolved.startswith(("http://", "https://")):
        return ArchiveUrl(url=resolved, hashed=bool(node.get("integrity")))
    return LocalPath(path=REPO_ROOT / "tools" / "gui" / resolved.removeprefix("file:"))


