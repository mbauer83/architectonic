"""RuntimeCatalogs — frozen bundle of all domain catalogs.

Built once at each composition root (FastAPI app-state, CLI main(), MCP context)
and injected into consumers. Never accessed via a global singleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.derivation.strategy_registry import DerivationStrategyCatalog
from src.application.guidance_composition import GuidanceContextView
from src.domain.modules.catalogs import ConnectionSemantics, DiagramTypeCatalog, OntologyCatalog
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.viewpoints.viewpoints import EnforcementSetting, ViewpointCatalog


@dataclass(frozen=True, eq=False)
class RuntimeCatalogs:
    """Immutable bundle of domain catalogs built once at the composition root."""

    module_catalog: ModuleCatalog
    ontology: OntologyCatalog
    connections: ConnectionSemantics
    diagram_types: DiagramTypeCatalog
    derivation: DerivationStrategyCatalog
    specializations: SpecializationCatalog = field(default_factory=SpecializationCatalog.empty)
    profiles: ProfileRegistry = field(default_factory=ProfileRegistry.empty)
    viewpoints: ViewpointCatalog = field(default_factory=ViewpointCatalog.empty)
    viewpoint_enforcement: EnforcementSetting = "warn"
    datatype_type_references_blocking: bool = True
    guidance_context: GuidanceContextView = field(default_factory=GuidanceContextView)
