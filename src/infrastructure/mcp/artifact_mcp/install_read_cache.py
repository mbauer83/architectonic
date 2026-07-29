"""Wrap pure read tools with the bounded, generation-keyed result cache.

Applied once, after registration, rather than as a decorator on each tool: the set of tools
that qualify is a policy statement, and keeping it in one list makes it reviewable. A tool
that reads git state, the assurance store, or the clock must never appear here — the
generation does not describe those, so a hit would serve something the stamp does not cover.

Degrades to no caching if FastMCP's internals move. The cache is an optimisation; losing it
must never take the read surface with it.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from src.infrastructure.mcp.artifact_mcp.read_result_cache import ReadResultCache

logger = logging.getLogger(__name__)

#: Read tools that are pure functions of the indexed model plus their arguments.
#:
#: Deliberately absent: `artifact_query_viewpoint` (the catalog is reloaded per request and
#: is not covered by the model generation) and `artifact_verify` (re-running it is the point).
CACHEABLE_READ_TOOLS: frozenset[str] = frozenset({
    "artifact_query_stats",
    "artifact_query_list_artifacts",
    "artifact_query_read_artifact",
    "artifact_query_search_artifacts",
    "artifact_query_find_connections_for",
    "artifact_query_find_neighbors",
    "artifact_query_datatype_types",
})


def generation_for(arguments: dict[str, Any]) -> int | None:
    """The generation that validates a result computed from *arguments*, if one exists.

    Resolved through the very helpers the tools use to pick their index, so the stamp always
    describes the store the answer actually came from. Deriving it from any single well-known
    index would be wrong the moment a call names a different `repo_root` or `repo_scope`: the
    result would carry a validator that cannot see the tree it was computed from, and a hit
    would survive edits it knows nothing about.

    None means "do not cache" — an index that cannot be resolved or has no version to report
    leaves nothing to invalidate against.
    """
    from src.infrastructure.mcp.artifact_mcp.context import (  # noqa: PLC0415
        repo_cached,
        resolve_repo_roots,
        roots_key,
    )

    try:
        roots = resolve_repo_roots(
            repo_scope=arguments.get("repo_scope", "both"),
            repo_root=arguments.get("repo_root"),
            repo_preset=arguments.get("repo_preset"),
            enterprise_root=arguments.get("enterprise_root"),
        )
        return int(repo_cached(roots_key(roots)).read_model_version().generation)
    except Exception:  # noqa: BLE001 — an unavailable generation means "do not cache"
        return None


def install_read_result_cache(mcp: Any, cache: ReadResultCache) -> int:
    """Wrap each cacheable registered tool. Returns how many were wrapped."""
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if not isinstance(tools, dict):
        logger.warning("MCP tool manager shape not recognised; read-result caching disabled")
        return 0

    wrapped = 0
    for name, tool in tools.items():
        if name not in CACHEABLE_READ_TOOLS:
            continue
        original: Callable[..., Any] | None = getattr(tool, "fn", None)
        if original is None or getattr(tool, "is_async", False):
            continue
        tool.fn = _memoized(name, original, cache)
        wrapped += 1
    return wrapped


def _memoized(name: str, original: Callable[..., Any], cache: ReadResultCache) -> Callable[..., Any]:
    signature = inspect.signature(original)

    @functools.wraps(original)
    def call(*args: Any, **kwargs: Any) -> Any:
        # Bound to parameter names so `f(x)` and `f(entity_id=x)` are one question rather than
        # two entries, and so `repo_root` can be read off the call however it was passed.
        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError:
            return original(*args, **kwargs)  # let the real call raise the real error
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        return cache.get_or_compute(
            name, arguments, generation_for(arguments), lambda: original(*args, **kwargs)
        )

    return call
