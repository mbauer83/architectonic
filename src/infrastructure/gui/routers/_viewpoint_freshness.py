"""Shared request-scoped freshness dependency for any GUI route that reads the viewpoint
catalog — split out of ``viewpoints.py`` so non-execution routes (e.g. authoring guidance)
can depend on it too, without duplicating the staleness fix.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import Depends

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.routers import state as s
from src.infrastructure.viewpoint_declarations import load_effective_viewpoint_catalog


def fresh_viewpoints_runtime_catalogs_dependency(
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> RuntimeCatalogs:
    """The installed `RuntimeCatalogs` with only `viewpoints` reloaded for this request —
    every route that reads the viewpoint catalog needs this. The module registry, ontology,
    and specialization catalogs are expensive to rebuild and change only on a real code/
    module change (a restart is the right time to pick those up), but an engagement-repo-
    authored viewpoint definition is ordinary data a user just wrote through the same
    request/response cycle. Without this, a newly-created definition could never be found
    by slug (nor appear in any viewpoint listing) until the process restarted — the exact
    staleness ``viewpoint_authoring.py``'s own endpoints already avoid (see its module
    docstring), using the same request-scoped ``load_effective_viewpoint_catalog`` rather
    than the fixed-workspace-config resolution ``app_bootstrap._load_viewpoints`` uses at
    startup."""
    return replace(catalogs, viewpoints=load_effective_viewpoint_catalog(list(s.get_repo().repo_roots)))
