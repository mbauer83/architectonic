"""ArchitectureEntityCreator adapter backed by the GUI backend's write path.

Implements the application ``ArchitectureEntityCreator`` port so the ModelAndBind
use case can create architecture entities (the Bound path) inside the unified GUI
backend, where architecture-write scope is available. Uses the same serialized
write path as ``POST /api/entities``.

The catalogs are constructor state, not something either method looks up. This adapter is built by
a request handler, which has them injected — and it needs them for two different reasons: to decide
whether an entity type may be authored at all, and to give the write path the verifier that will
check the result. Both used to reach for process state, so a test overriding the catalogs configured
neither.
"""

from __future__ import annotations

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.modules.module_types import EntityTypeName
from src.domain.repository.groups import UNCATEGORIZED


class GuiArchitectureEntityCreator:
    """Create architecture entities via the backend's serialized write queue."""

    def __init__(self, catalogs: RuntimeCatalogs) -> None:
        self._catalogs = catalogs

    def is_known_type(self, artifact_type: str) -> bool:
        from src.application.entity_type_predicates import is_internal_entity_type  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

        registry = get_module_registry()
        if registry.find_entity_type(EntityTypeName(artifact_type)) is None:
            return False
        # Internal global-artifact-reference types cannot be authored directly.
        return not is_internal_entity_type(artifact_type, self._catalogs.ontology)

    def create(self, artifact_type: str, name: str) -> str:
        from src.infrastructure.rest.routers import state as s  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.entity import create_entity as _create  # noqa: PLC0415

        repo_root, _registry, verifier = s.get_write_deps(self._catalogs)
        # Same authorization identity as POST /api/entities — this adapter creates an
        # ordinary engagement entity on behalf of the assurance model-and-bind flow.
        result = s.authorized_write(
            "entities_create_entity",
            _create,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_type=artifact_type,
            name=name,
            summary=None,
            properties=None,
            attribute_types=None,
            notes=None,
            keywords=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=False,
            group=UNCATEGORIZED,
        )
        if not result.wrote:
            detail = "; ".join(result.warnings) if result.warnings else "unknown error"
            raise RuntimeError(f"architecture entity creation failed: {detail}")
        return result.artifact_id
