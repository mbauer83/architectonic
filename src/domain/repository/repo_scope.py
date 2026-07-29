"""Pure path-heuristic repo scope classification (no config/YAML access)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

MountScope = Literal["engagement", "enterprise"]


def infer_repo_scope(path: Path) -> MountScope:
    """Classify a repo root as engagement or enterprise using directory-name heuristics."""
    parts = path.resolve().parts
    if "engagements" in parts:
        return "engagement"
    if "enterprise-repository" in parts:
        return "enterprise"
    return "engagement"
