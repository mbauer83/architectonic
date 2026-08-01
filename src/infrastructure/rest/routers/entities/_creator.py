"""ArchitectureEntityCreator adapter backed by the GUI backend's write path.

Implements the application ``ArchitectureEntityCreator`` port so the ModelAndBind
use case can create architecture entities (the Bound path) inside the unified GUI
backend, where architecture-write scope is available. Uses the same serialized
write path as ``POST /api/entities``.
"""

from __future__ import annotations

from src.domain.modules.module_types import EntityTypeName
from src.domain.repository.groups import UNCATEGORIZED


class GuiArchitectureEntityCreator:
    """Create architecture entities via the backend's serialized write queue."""

    def is_known_type(self, artifact_type: str) -> bool:
        from src.application.entity_type_predicates import is_internal_entity_type  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import (  # noqa: PLC0415
            build_runtime_catalogs,
            get_module_registry,
        )

        registry = get_module_registry()
        if registry.find_entity_type(EntityTypeName(artifact_type)) is None:
            return False
        # Internal global-artifact-reference types cannot be authored directly.
        return not is_internal_entity_type(artifact_type, build_runtime_catalogs(registry).ontology)

    def create(self, artifact_type: str, name: str) -> str:
        from src.infrastructure.rest.routers import state as s  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.entity import create_entity as _create  # noqa: PLC0415

        repo_root, _registry, verifier = s.get_write_deps()
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
