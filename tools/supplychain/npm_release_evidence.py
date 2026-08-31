#!/usr/bin/env python
"""When each locked npm version was published, from committed evidence first and the registry second.

`package-lock.json` records no publish time, and npm's abbreviated packument does not carry one
either, so the only source is the full packument — 300 KB compressed for a package with many
versions, measured. Asking the registry for all 455 pins on every gate run would make the gate slow,
network-dependent and rate-limited, which is how a supply-chain gate ends up disabled.

So the evidence is committed. The rule is monotone — a version's publish time never changes, and a
pin that cleared the floor stays clear — which is exactly what makes a recorded answer as good as a
fresh one. A pin with no recorded answer is queried live, and the record is refreshed with `--write`.

**A query that cannot be answered fails the gate.** A supply-chain control that passes when it could
not check is the same confident non-answer as an audit run against the wrong environment.
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "supplychain" / "npm-publish-times.json"

_REGISTRY = "https://registry.npmjs.org"
_TIMEOUT_SECONDS = 30


class RegistryUnavailable(RuntimeError):
    """The registry was asked when a pin was published and could not answer."""


def pin(name: str, version: str) -> str:
    """The key a publish time is recorded under. One spelling, used by the reader and the writer."""
    return f"{name}@{version}"


def recorded_times(evidence: Path = EVIDENCE) -> Mapping[str, str]:
    if not evidence.exists():
        return {}
    document = json.loads(evidence.read_text(encoding="utf-8"))
    published = document.get("published", {})
    return {str(key): str(value) for key, value in published.items()}


def render(published: Mapping[str, str]) -> str:
    return json.dumps(
        {"registry": _REGISTRY, "count": len(published),
         "published": {key: published[key] for key in sorted(published)}},
        indent=2,
    ) + "\n"


class PublishTimes:
    """Publish times for locked pins: committed evidence, with the registry as the fallback.

    Packuments fetched during a run are kept, because a lockfile names many versions of few packages.
    """

    def __init__(
        self,
        recorded: Mapping[str, str],
        fetch: Callable[[str], Mapping[str, str]] | None = None,
    ) -> None:
        self._recorded = dict(recorded)
        self._fetch = fetch if fetch is not None else fetch_package_times
        self._fetched: dict[str, Mapping[str, str]] = {}
        self._queried: set[str] = set()

    @property
    def queried(self) -> frozenset[str]:
        """The pins this run had to ask the registry about — what `--write` would record."""
        return frozenset(self._queried)

    def observed(self) -> Mapping[str, str]:
        """Everything known after the run: what was recorded, plus what was answered live."""
        return {**self._recorded, **{key: self._live(key) for key in sorted(self._queried)}}

    def of(self, name: str, version: str) -> datetime:
        key = pin(name, version)
        stamp = self._recorded.get(key) or self._live(key)
        parsed = _parsed(stamp)
        if parsed is None:
            raise RegistryUnavailable(f"{key}: publish time {stamp!r} is not a timestamp")
        return parsed

    def _live(self, key: str) -> str:
        name, _, version = key.rpartition("@")
        if name not in self._fetched:
            self._fetched[name] = self._fetch(name)
        published = self._fetched[name].get(version)
        if published is None:
            raise RegistryUnavailable(f"{key}: the registry lists no publish time for this version")
        self._queried.add(key)
        return published


def fetch_package_times(name: str) -> Mapping[str, str]:
    """`version -> publish time` for one package, from its full packument."""
    request = urllib.request.Request(
        f"{_REGISTRY}/{urllib.parse.quote(name, safe='@')}",
        headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as answer:
            payload = answer.read()
            if answer.headers.get("Content-Encoding") == "gzip":
                payload = gzip.decompress(payload)
    except (urllib.error.URLError, OSError, gzip.BadGzipFile) as unreachable:
        raise RegistryUnavailable(f"{name}: {unreachable}") from unreachable
    times = json.loads(payload).get("time", {})
    return {str(key): str(value) for key, value in times.items() if key not in ("created", "modified")}


def _parsed(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
