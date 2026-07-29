"""On-demand, never-persisted memoisation of ``reference_report``.

The report is a pure function of (definition, current model). Persisting it would repeat the
rename-stale-index failure mode and would not self-clear when the model changes back, so it
is recomputed on demand and cached only in-process, keyed by ``(index_generation, definition
digest)`` — the same staleness key fork status uses.

SOUNDNESS INVARIANT: the registries and read model passed to a given ``index_generation`` are
a pure function OF that generation — any model revision (including retiring a type, which is
itself an artifact edit) bumps the generation. So a bumped generation or an edited definition
(new digest) is a cache miss and a reference that comes back self-heals. When
``index_generation`` is ``None`` (ad-hoc execution with no model-version stamp) the cache is
bypassed entirely, so callers that vary the registries independently of a generation stamp
never observe a stale hit.
"""

from __future__ import annotations

from collections import OrderedDict

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess
from src.domain.viewpoints.viewpoint_lineage import definition_digest
from src.domain.viewpoints.viewpoint_reference_report import BrokenReference, reference_report
from src.domain.viewpoints.viewpoints import ViewpointDefinition

_CACHE_MAX = 512
_cache: "OrderedDict[tuple[int, str], tuple[BrokenReference, ...]]" = OrderedDict()


def cached_reference_report(
    definition: ViewpointDefinition,
    *,
    registries: RegistrySnapshot,
    read_access: CriteriaReadAccess,
    index_generation: int | None,
) -> tuple[BrokenReference, ...]:
    if index_generation is None:
        return reference_report(definition, registries=registries, read_access=read_access)
    key = (index_generation, definition_digest(definition))
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    report = reference_report(definition, registries=registries, read_access=read_access)
    _cache[key] = report
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return report


def clear_reference_report_cache() -> None:
    """Test hook: drop all memoised reports (the cache is otherwise process-lived)."""
    _cache.clear()
