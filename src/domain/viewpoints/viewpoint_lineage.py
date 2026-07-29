"""Fork lineage computation for viewpoint definitions.

A fork's provenance must bind to IMMUTABLE content: versions are hand-edited integers, so
``slug + version`` alone cannot establish what a fork was forked from. Lineage therefore
carries a canonical content digest of the origin at fork time (plus the model index
generation), and staleness is decided by digest comparison — editing the origin flips
every fork's badge even when nobody bumped the origin's version integer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from src.domain.viewpoints.viewpoint_serialization import viewpoint_definition_to_mapping
from src.domain.viewpoints.viewpoints import ForkLineage, ViewpointDefinition

ForkStatus = Literal["current", "stale", "origin-missing"]


def definition_digest(definition: ViewpointDefinition) -> str:
    """Canonical content hash of a definition — its serialized mapping minus provenance
    (a definition's own lineage is not part of what it SAYS), JSON-canonicalized so key
    order and formatting can never affect identity."""
    mapping = viewpoint_definition_to_mapping(definition)
    mapping.pop("forked_from", None)
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fork_lineage(origin: ViewpointDefinition, index_generation: int | None) -> ForkLineage:
    return ForkLineage(
        slug=origin.slug,
        version=origin.version,
        definition_digest=definition_digest(origin),
        index_generation=index_generation,
    )


def fork_status(lineage: ForkLineage | None, current_origin: ViewpointDefinition | None) -> ForkStatus | None:
    """``None`` for a non-fork; ``origin-missing`` when the recorded origin slug no longer
    resolves; otherwise ``current``/``stale`` by content-digest comparison."""
    if lineage is None:
        return None
    if current_origin is None:
        return "origin-missing"
    return "current" if definition_digest(current_origin) == lineage.definition_digest else "stale"
