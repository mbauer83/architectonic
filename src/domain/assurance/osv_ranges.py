"""OSV affected-range applicability evaluation.

Per-ecosystem version comparison adapters (PyPI via `packaging`, npm via a
minimal strict semver) and OSV event semantics: an affected interval starts at
``introduced`` and ends at ``fixed`` (exclusive) or ``last_affected``
(inclusive), never extending past ``limit``. ``GIT``/commit ranges are
provenance only — recorded upstream, never evaluated here. Anything
uncomparable (unknown ecosystem, unparsable version) is ``unknown``, never
silently not-applicable.
"""

from __future__ import annotations

from typing import Callable, Literal, Mapping, Sequence

from packaging.version import InvalidVersion, Version

Applicability = Literal["applicable", "not_applicable", "unknown"]


def _pypi_key(version: str) -> Version | None:
    try:
        return Version(version)
    except InvalidVersion:
        return None


def _npm_key(version: str) -> tuple[object, ...] | None:
    """Minimal strict semver: MAJOR.MINOR.PATCH with optional pre-release; a
    pre-release sorts before its release (semver §11)."""
    body, _, prerelease = version.strip().lstrip("v").partition("-")
    parts = body.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    numbers = tuple(int(p) for p in parts)
    if not prerelease:
        return (*numbers, 1, ())
    identifiers: list[tuple[int, object]] = [
        (0, int(ident)) if ident.isdigit() else (1, ident)
        for ident in prerelease.split(".")
    ]
    return (*numbers, 0, tuple(identifiers))


_ECOSYSTEM_KEYS: Mapping[str, Callable[[str], object | None]] = {
    "pypi": _pypi_key,
    "npm": _npm_key,
}


def comparable_key(ecosystem: str, version: str) -> object | None:
    parser = _ECOSYSTEM_KEYS.get(ecosystem.lower())
    return None if parser is None else parser(version)


def _interval_hits(
    key: object,
    events: Sequence[Mapping[str, str]],
    parse: Callable[[str], object | None],
) -> Applicability:
    introduced: list[object] = []
    closers: list[tuple[object, bool]] = []  # (bound, inclusive)
    for event in events:
        if "introduced" in event:
            raw = event["introduced"]
            if raw == "0":
                introduced.append(None)  # -infinity
                continue
            parsed = parse(raw)
            if parsed is None:
                return "unknown"
            introduced.append(parsed)
        elif "fixed" in event or "limit" in event:
            parsed = parse(event.get("fixed") or event["limit"])
            if parsed is None:
                return "unknown"
            closers.append((parsed, False))
        elif "last_affected" in event:
            parsed = parse(event["last_affected"])
            if parsed is None:
                return "unknown"
            closers.append((parsed, True))
    for start in introduced:
        if start is not None and key < start:  # type: ignore[operator]
            continue
        # In range unless a closer at/below cuts it off before the key.
        closed = any(
            (key >= bound if not inclusive else key > bound)  # type: ignore[operator]
            and (start is None or bound >= start)  # type: ignore[operator]
            for bound, inclusive in closers
        )
        if not closed:
            return "applicable"
    return "not_applicable"


def evaluate_applicability(
    ecosystem: str,
    version: str,
    affected_entries: Sequence[Mapping[str, object]],
) -> Applicability:
    """Applicability of (ecosystem, version) across an OSV record's affected
    entries: exact `versions` membership wins; otherwise ECOSYSTEM/SEMVER range
    intervals; commit ranges are skipped (provenance only); no evaluable signal
    at all ⇒ unknown."""
    parse = _ECOSYSTEM_KEYS.get(ecosystem.lower())
    key = parse(version) if parse is not None else None
    saw_evaluable = False
    outcome: Applicability = "not_applicable"
    for entry in affected_entries:
        versions = entry.get("versions")
        if isinstance(versions, list) and versions:
            saw_evaluable = True
            if version in [str(v) for v in versions]:
                return "applicable"
        ranges = entry.get("ranges")
        if not isinstance(ranges, list):
            continue
        for rng in ranges:
            if not isinstance(rng, Mapping):
                continue
            range_type = str(rng.get("type", "")).upper()
            if range_type == "GIT":
                continue  # provenance only
            events = rng.get("events")
            if not isinstance(events, list):
                continue
            saw_evaluable = True
            if key is None:
                return "unknown"
            verdict = _interval_hits(key, events, parse)  # type: ignore[arg-type]
            if verdict == "applicable":
                return "applicable"
            if verdict == "unknown":
                outcome = "unknown"
    if not saw_evaluable:
        return "unknown"
    return outcome
