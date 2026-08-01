"""The one place the assurance surfaces obtain the architecture graph.

Every failure-mode read path needs the same view of the public model, and each one resolving its
own repository would be three chances for them to disagree about which workspace is being analysed
— a matrix and an entity page reporting different candidates for the same element.

The repository is taken from the running process's shared index rather than opened again. This
backend serves the GUI, the REST API and both MCP servers together, so the index is already loaded
and already kept current by the watcher; opening a second one would answer from a snapshot that
drifts. Where no index is loaded — an MCP server run standalone, a test staging only a store — the
empty basis is returned, and the surfaces degrade to the analyst's own bindings rather than failing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.assurance.arch_ref_resolver import ArchitectureEntityLookup

from functools import lru_cache

from src.application.assurance_fmea_architecture import (
    ArchitectureBasis,
    ArchitectureModelSource,
    ConnectionTypeSource,
    EntityTypeSource,
    read_architecture_basis,
)


@lru_cache(maxsize=1)
def _ontology() -> ConnectionTypeSource:
    """The ontology catalog, built once — it is configuration, not model content.

    Serves both type questions the basis asks: a connection's derivation role and strength, and an
    entity's domain and classes. One catalog rather than two lookups, because they are one source.
    """
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry()).ontology


def _shared_repository() -> ArchitectureModelSource | None:
    """The process's loaded architecture index, or None when nothing has loaded one.

    Imported defensively for the same reason the artifact MCP context does: the assurance servers
    are startable without the GUI, and an ImportError there must read as "no model available"
    rather than take down a read that has a sound answer without one.
    """
    try:
        from src.infrastructure.rest.routers import state as gui_state  # noqa: PLC0415
    except ImportError:
        return None
    return gui_state.maybe_get_repo()


def shared_artifact_lookup() -> "ArchitectureEntityLookup | None":
    """The process's architecture index, for callers that need to look ids up directly.

    Goes to the shared repository rather than through `_shared_repository`, whose return
    type is deliberately narrowed to the two graph reads the basis needs — point lookup is
    a different question and needs the lookup port. Same defensiveness: absent when the
    assurance servers run without a loaded model, in which case a caller must report that
    it could not check rather than that it found nothing.
    """
    try:
        from src.infrastructure.rest.routers import state as gui_state  # noqa: PLC0415
    except ImportError:
        return None
    return gui_state.maybe_get_repo()


def current_architecture_basis() -> ArchitectureBasis:
    """Assemble the graph for this request.

    Deliberately not cached: it is model content, and a stale graph would report a candidate that
    has since been deleted or miss one just added. The cost is one pass over connections and
    entities, paid once per matrix read rather than once per row.
    """
    catalog = _ontology()
    # The same catalog answers both type questions, so the runtime_checkable guard is about honesty
    # rather than dispatch: a catalog that cannot say which types act yields an empty analysable set,
    # and the checks that need it report nothing instead of guessing.
    return read_architecture_basis(
        _shared_repository(),
        connection_types=catalog,
        entity_types=catalog if isinstance(catalog, EntityTypeSource) else None,
    )
