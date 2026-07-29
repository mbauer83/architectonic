"""Viewpoint pins: an engagement-repo-local sidecar list of pinned definition slugs for
quick access (Home surfacing, management-view rows). Not definition content — pinning a
module/enterprise-shipped (read-only) definition is fine, and pins are never promoted
(promotion transfers artifact files; this sidecar list is never one).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.domain.repository.repo_layout import ARCH_REPO

_PINS_FILE = "viewpoint-pins.yaml"


@dataclass(frozen=True)
class PinnedSlugs:
    slugs: tuple[str, ...]  # known, deduplicated, file order preserved
    pruned: tuple[str, ...]  # unknown slugs dropped from ``slugs`` — surface as a warning


def _pins_path(repo_root: Path) -> Path:
    return repo_root / ARCH_REPO / _PINS_FILE


def _deduplicated(slugs: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for slug in slugs:
        if slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return tuple(ordered)


def load_pinned_slugs(repo_root: Path, *, known_slugs: frozenset[str]) -> PinnedSlugs:
    """Absence = no pins. Slugs no longer in ``known_slugs`` (a definition later removed
    from the catalog) are dropped from ``slugs`` and reported in ``pruned`` — the file
    itself is left untouched; pruning only happens for the caller who chooses to persist."""
    path = _pins_path(repo_root)
    if not path.exists():
        return PinnedSlugs(slugs=(), pruned=())
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw = loaded if isinstance(loaded, list) else []
    ordered = _deduplicated(tuple(str(item) for item in raw))
    kept = tuple(slug for slug in ordered if slug in known_slugs)
    pruned = tuple(slug for slug in ordered if slug not in known_slugs)
    return PinnedSlugs(slugs=kept, pruned=pruned)


def save_pinned_slugs(repo_root: Path, slugs: tuple[str, ...]) -> None:
    path = _pins_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.dump(list(_deduplicated(slugs)), default_flow_style=False, allow_unicode=True, sort_keys=False)
    path.write_text(dumped if isinstance(dumped, str) else "", encoding="utf-8")
