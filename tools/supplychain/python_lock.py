#!/usr/bin/env python
"""Read `uv.lock` into the entries the release-age policy judges.

The Python half needs no registry calls at all: `uv.lock` records an `upload-time` on every sdist and
wheel it pins, so the evidence the floor needs is already committed alongside the pins it describes.

Every lock entry is read, not a closure. `check_licenses.py` exports with `--no-emit-project`, so the
shipped closure excludes the editable project while the lock contains it — and the age floor has to
have an answer for the project's own entry rather than a hole where it would be.

An unrecognised source shape is refused rather than skipped. A supply-chain gate that passes what it
does not understand is the same non-answer as an audit that ran over the wrong environment.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.supplychain.release_age import (
    ArchiveUrl,
    LocalPath,
    LockedPackage,
    RegistryArtifacts,
    Source,
    vcs_ref,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "uv.lock"


class UnreadableLockEntry(ValueError):
    """A lock entry whose source shape this reader does not know how to judge."""


def locked_packages(lock: Path = LOCK) -> tuple[LockedPackage, ...]:
    document = tomllib.loads(lock.read_text(encoding="utf-8"))
    return tuple(
        LockedPackage(name=entry["name"], version=entry.get("version", ""), source=_source_of(entry))
        for entry in document.get("package", ())
    )


def _source_of(entry: dict[str, Any]) -> Source:
    source = entry.get("source", {})
    match sorted(source):
        case ["registry"]:
            return RegistryArtifacts(uploaded=_upload_times(entry))
        case ["editable"] | ["directory"] | ["virtual"] | ["path"]:
            # uv writes these relative to the project, so they resolve against the repository root.
            return LocalPath(path=REPO_ROOT / str(next(iter(source.values()))))
        case ["url"]:
            return ArchiveUrl(url=str(source["url"]), hashed=bool(entry.get("sdist", {}).get("hash")))
        case _ if "git" in source:
            return vcs_ref(str(source["git"]))
    raise UnreadableLockEntry(
        f"{entry.get('name', '?')}: unrecognised source {sorted(source)}. Teach "
        "`tools/supplychain/python_lock.py` what it is and give it a verdict in `release_age`; do "
        "not let a shape the gate cannot judge pass unjudged."
    )


def _upload_times(entry: dict[str, Any]) -> tuple[datetime | None, ...]:
    """One entry per locked artifact — the sdist and every wheel — in the order the lock names them."""
    artifacts = [entry["sdist"]] if "sdist" in entry else []
    artifacts.extend(entry.get("wheels", ()))
    return tuple(_parsed(artifact.get("upload-time")) for artifact in artifacts)


def _parsed(stamp: object) -> datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
