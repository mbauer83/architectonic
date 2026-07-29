"""Effective connection-endpoint semantics for global-artifact-reference proxies.

A GAR is not a modelling element — it proxies exactly one global (enterprise) artifact.
Its connection surface is therefore EXACTLY the referenced entity type's (and
specialization's) surface, with one tier invariant on top: the global object — and thus
its reference — must never be the SOURCE of a directed relationship (the enterprise tier
never depends on engagement content). Only incoming and symmetric relationships may
attach to a GAR.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.verification.artifact_verifier_parsing import parse_frontmatter_from_path
from src.application.verification.artifact_verifier_registry import ArtifactRegistry

GLOBAL_ARTIFACT_REFERENCE_TYPE = "global-artifact-reference"
_GLOBAL_ID_KEY = "global-artifact-id"
_GLOBAL_ENTITY_TYPE_KEY = "global-artifact-entity-type"


@dataclass(frozen=True)
class EffectiveEndpoint:
    """One connection endpoint with GAR proxies resolved to what they reference."""

    entity_type: str | None
    specialization: str
    is_global_reference: bool


def _frontmatter(registry: ArtifactRegistry, entity_id: str) -> dict[str, object] | None:
    path = registry.find_file_by_id(entity_id)
    if path is None:
        return None
    fm = parse_frontmatter_from_path(path)
    return fm if isinstance(fm, dict) else None


def effective_endpoint(registry: ArtifactRegistry, entity_id: str) -> EffectiveEndpoint:
    """The endpoint's connection-legality identity.

    A plain entity resolves to its own type and specialization. A GAR resolves to the
    REFERENCED global entity's type and specialization (read from the enterprise record
    when reachable, falling back to the type the proxy's frontmatter caches), so pair
    legality is judged against what the proxy stands for, never against the proxy's
    internal type."""
    fm = _frontmatter(registry, entity_id)
    if fm is None:
        return EffectiveEndpoint(entity_type=None, specialization="", is_global_reference=False)
    own_type = str(fm.get("artifact-type", "")) or None
    if own_type != GLOBAL_ARTIFACT_REFERENCE_TYPE:
        return EffectiveEndpoint(
            entity_type=own_type,
            specialization=str(fm.get("specialization", "") or ""),
            is_global_reference=False,
        )
    referenced_id = str(fm.get(_GLOBAL_ID_KEY, "") or "")
    referenced_fm = _frontmatter(registry, referenced_id) if referenced_id else None
    if referenced_fm is not None:
        return EffectiveEndpoint(
            entity_type=str(referenced_fm.get("artifact-type", "")) or None,
            specialization=str(referenced_fm.get("specialization", "") or ""),
            is_global_reference=True,
        )
    cached_type = str(fm.get(_GLOBAL_ENTITY_TYPE_KEY, "") or "")
    return EffectiveEndpoint(entity_type=cached_type or None, specialization="", is_global_reference=True)


GLOBAL_REFERENCE_SOURCE_ERROR = (
    "A global reference cannot be the source of a directed relationship — the enterprise "
    "tier never depends on engagement content. Only incoming and symmetric relationships "
    "may attach to a global reference."
)
