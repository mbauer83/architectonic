"""Application startup wiring for the module registry and runtime catalogs."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Request

from src.application.assurance_edge_catalog import EdgeCatalogSource
from src.application.derivation.strategy_registry import DerivationStrategyCatalogBuilder
from src.application.guidance_composition import ComposedContext, GuidanceContextView
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.startup_validation import validate_registry_consistency
from src.config.settings import datatype_type_references_blocking, viewpoint_enforcement_setting
from src.config.workspace_paths import resolve_workspace_repo_roots
from src.diagram_types import register_default_diagram_types
from src.domain.guidance.guidance import GuidanceOverlay
from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy
from src.domain.modules.catalogs import (
    ConnectionSemanticsImpl,
    DiagramTypeCatalog,
    DiagramTypeCatalogImpl,
    OntologyCatalogImpl,
)
from src.domain.modules.module_catalog import ModuleCatalog, ModuleCatalogBuilder
from src.domain.modules.module_filter import is_module_enabled
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.domain.ontology_representation.profile_registry import merge_profile_registries
from src.domain.ontology_representation.specializations import SpecializationCatalog, merge_specialization_catalogs
from src.domain.viewpoints.viewpoints import ViewpointCatalog
from src.infrastructure.assurance.capability import make_capability
from src.infrastructure.guidance_cache import load_guidance_overlay, load_workspace_guidance
from src.infrastructure.rendering._svg_sprite_convert import browser_markup_to_plantuml_svg as _svg_convert
from src.infrastructure.specialization_declarations import load_specialization_catalog_for_repos
from src.infrastructure.viewpoint_declarations import (
    load_module_viewpoint_catalog,
    load_viewpoint_catalog_for_repos,
)
from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCH_PACKAGE_DIR
from src.ontologies.archimate_4._loader import META_ONTOLOGY_ALIAS as _ARCHIMATE_META_ALIAS
from src.ontologies.archimate_4._loader import load_archimate_4_module
from src.ontologies.assurance._loader import _PACKAGE_DIR as _ASSURANCE_PACKAGE_DIR
from src.ontologies.assurance._loader import META_ONTOLOGY_ALIAS as _ASSURANCE_META_ALIAS
from src.ontologies.assurance._loader import load_assurance_module
from src.ontologies.sysml_v2_min._loader import _PACKAGE_DIR as _SYSML_PACKAGE_DIR
from src.ontologies.sysml_v2_min._loader import META_ONTOLOGY_ALIAS as _SYSML_META_ALIAS
from src.ontologies.sysml_v2_min._loader import load_sysml_module


def _load_guidance_overlay(alias: str) -> GuidanceOverlay:
    """Load the one deployment-level guidance cache for one meta-ontology alias.

    Guidance is a deployment concern, not a per-repository-tier one: one running instance of
    this software pulls one guidance source, imported once into a local, out-of-repo cache
    file and integrated into the in-memory meta-ontology representation at bootstrap — never
    per engagement/enterprise repo. No cache present (e.g. code generation, most unit tests,
    or before the first import) ⇒ empty overlay, a no-op — entities keep whatever
    ``create_when``/``never_create_when`` text the module ships inline. A guidance import
    takes effect on the next backend restart, since this runs once at process/module-import
    time (consistent with the existing ``@lru_cache`` registry pattern).
    """
    return load_guidance_overlay(alias)


def _load_archimate_specializations() -> SpecializationCatalog:
    roots = resolve_workspace_repo_roots()
    if roots is None:
        return SpecializationCatalog.empty()
    engagement_root, enterprise_root = roots
    return load_specialization_catalog_for_repos(
        _ARCHIMATE_META_ALIAS,
        enterprise_root=enterprise_root,
        engagement_root=engagement_root,
    )


def _load_viewpoints() -> ViewpointCatalog:
    """Module-shipped starter library merged with the repo two-tier override, like
    specializations. Registry-aware validation runs separately once the full runtime
    catalogs are assembled, not here."""
    module_catalog = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR)
    roots = resolve_workspace_repo_roots()
    if roots is None:
        return module_catalog
    engagement_root, enterprise_root = roots
    repo_catalog = load_viewpoint_catalog_for_repos(enterprise_root=enterprise_root, engagement_root=engagement_root)
    return module_catalog | repo_catalog


_archimate_4_module = load_archimate_4_module(
    _ARCH_PACKAGE_DIR,
    svg_converter=_svg_convert,
    guidance=_load_guidance_overlay(_ARCHIMATE_META_ALIAS),
    specializations=_load_archimate_specializations(),
)
_archimate_matrix_abbreviations = _archimate_4_module.matrix_abbreviations

_sysml_v2_min_module = load_sysml_module(_SYSML_PACKAGE_DIR, guidance=_load_guidance_overlay(_SYSML_META_ALIAS))
_assurance_module = load_assurance_module(
    _ASSURANCE_PACKAGE_DIR, guidance=_load_guidance_overlay(_ASSURANCE_META_ALIAS)
)

_MODULE_REGISTRY_STATE_KEY = "module_registry"
_RUNTIME_CATALOGS_STATE_KEY = "runtime_catalogs"
_logger = logging.getLogger(__name__)

_ALL_ONTOLOGY_MODULES = (_archimate_4_module, _sysml_v2_min_module, _assurance_module)

_DEFAULT_ASSURANCE_DB = Path(__file__).resolve().parents[2] / ".arch-assurance" / "store.db"


def _inject_capability_sentinels(registered_names: set[str]) -> None:
    """Add synthetic capability names before module deps are checked.

    confidential_store: present when the keychain key + DB file are available.
    """
    capability = make_capability(_DEFAULT_ASSURANCE_DB)
    if capability.enabled:
        registered_names.add("confidential_store")
        _logger.info("confidential_store capability available at %s", _DEFAULT_ASSURANCE_DB)


def build_module_registry(*, complete_vocabulary: bool = False) -> ModuleRegistry:
    """Assemble the module registry from the configured ontology and diagram-type modules.

    complete_vocabulary: register every module and diagram type unconditionally, ignoring
    optional runtime capabilities (e.g. the confidential assurance store) and local YAML
    overrides. Code generation and schema export use this so the emitted vocabulary is the
    full, stable superset regardless of the environment it runs in — otherwise the output
    would differ between a machine that has the assurance store and one that does not.
    """
    from src.config.settings import module_overrides  # noqa: PLC0415

    overrides = module_overrides()
    registry = ModuleRegistry()
    registered_names: set[str] = set()

    _inject_capability_sentinels(registered_names)

    for om in _ALL_ONTOLOGY_MODULES:
        if complete_vocabulary or is_module_enabled(om, overrides, registered_names):
            registry.register_ontology(om)
            registered_names.add(om.name)
        else:
            _logger.info("Ontology module %r skipped (disabled or unsatisfied requires)", om.name)

    if complete_vocabulary:
        register_default_diagram_types(registry)
    else:
        register_default_diagram_types(registry, overrides=overrides, registered_names=registered_names)
    validate_registry_consistency(registry)
    return registry


def build_module_catalog(registry: ModuleRegistry) -> ModuleCatalog:
    """Convert a ModuleRegistry snapshot into an immutable ModuleCatalog."""
    builder = ModuleCatalogBuilder()
    for om in registry.all_ontologies().values():
        builder.register_ontology(om)
    for dt in registry.all_diagram_types().values():
        builder.register_diagram_type(dt)
    return builder.build()


def _build_derivation_catalog():
    from src.application.derivation import (  # noqa: PLC0415
        derived_relationships,
        explicit_selection,
        incident_connections,
        local_neighborhood,
        path_projection,
        viewpoint_execution,
    )
    from src.diagram_types.c4._projection import MANIFEST as _c4_manifest  # noqa: PLC0415
    from src.infrastructure.derivation_strategy_wiring import (  # noqa: PLC0415
        derived_relationships_derive,
        viewpoint_execution_derive,
    )

    builder = DerivationStrategyCatalogBuilder()
    builder.register(explicit_selection.SPEC, explicit_selection.derive)
    builder.register(local_neighborhood.SPEC, local_neighborhood.derive)
    builder.register(incident_connections.SPEC, incident_connections.derive)
    builder.register(path_projection.SPEC, path_projection.derive)
    builder.register(viewpoint_execution.SPEC, viewpoint_execution_derive)
    builder.register(derived_relationships.SPEC, derived_relationships_derive)
    for spec, fn in _c4_manifest.strategies:
        builder.register(spec, fn)
    return builder.build()


_GUIDANCE_ALIASES = (_ARCHIMATE_META_ALIAS, _SYSML_META_ALIAS, _ASSURANCE_META_ALIAS)


def _guidance_modules(registry: ModuleRegistry) -> dict[str, OntologyModule]:
    """Every guidance-carrying meta-ontology that resolves in ``registry``, by alias — the one place
    that knows which aliases can carry guidance."""
    resolved = ((alias, resolve_meta_ontology_module(alias, registry)) for alias in _GUIDANCE_ALIASES)
    return {alias: module for alias, module in resolved if module is not None}


def guidance_hierarchies(registry: ModuleRegistry) -> dict[str, GuidanceHierarchy]:
    """The declared guidance tree of each of those meta-ontologies, so serving (the layered-context
    view) and the operational guidance-cache migration read the same trees."""
    from src.domain.guidance.guidance_hierarchy_source import resolve_guidance_hierarchy  # noqa: PLC0415

    return {
        alias: resolve_guidance_hierarchy(module, alias=alias)
        for alias, module in _guidance_modules(registry).items()
    }


def _build_guidance_context_view(registry: ModuleRegistry) -> GuidanceContextView:
    """Assemble the serving-time layered-guidance context view, keyed by meta-ontology alias.

    Each meta-ontology's cache is loaded once and paired with its derived hierarchy; only
    aliases that actually carry context are indexed. Entity type names map back to their owning
    alias so ``get_type_guidance`` can compose a type's ancestry context without touching the
    cache or hierarchy itself.
    """
    from src.domain.guidance.guidance_hierarchy_source import resolve_guidance_hierarchy  # noqa: PLC0415

    sources: dict[str, tuple[GuidanceHierarchy, GuidanceOverlay]] = {}
    type_alias: dict[str, str] = {}
    for alias, module in _guidance_modules(registry).items():
        overlay = _load_guidance_overlay(alias)
        if not overlay.context_entries:
            continue
        sources[alias] = (resolve_guidance_hierarchy(module, alias=alias), overlay)
        for type_name in module.entity_types:
            type_alias.setdefault(str(type_name), alias)
    workspace = load_workspace_guidance()
    workspace_layers = (
        () if workspace.is_empty()
        else (ComposedContext(level_id="workspace", node_id="workspace", text=workspace.context),)
    )
    return GuidanceContextView(sources=sources, type_alias=type_alias, workspace=workspace_layers)


def build_runtime_catalogs(registry: ModuleRegistry) -> RuntimeCatalogs:
    """Build a frozen RuntimeCatalogs from a fully-built ModuleRegistry."""
    module_catalog = build_module_catalog(registry)
    specializations = merge_specialization_catalogs(
        *(module.specialization_catalog for module in module_catalog.all_ontologies().values())
    )
    profiles = merge_profile_registries(
        module.profile_registry for module in module_catalog.all_ontologies().values()
    )
    return RuntimeCatalogs(
        module_catalog=module_catalog,
        ontology=OntologyCatalogImpl(module_catalog, _archimate_matrix_abbreviations),
        connections=ConnectionSemanticsImpl(module_catalog),
        diagram_types=DiagramTypeCatalogImpl(module_catalog),
        derivation=_build_derivation_catalog(),
        specializations=specializations,
        profiles=profiles,
        viewpoints=_load_viewpoints(),
        viewpoint_enforcement=viewpoint_enforcement_setting(),
        datatype_type_references_blocking=datatype_type_references_blocking(),
        guidance_context=_build_guidance_context_view(registry),
    )


def install_module_registry(app: Any, *, registry: ModuleRegistry | None = None) -> ModuleRegistry:
    """Attach the module registry and runtime catalogs to FastAPI app state."""
    resolved = registry or get_module_registry()
    setattr(app.state, _MODULE_REGISTRY_STATE_KEY, resolved)
    setattr(app.state, _RUNTIME_CATALOGS_STATE_KEY, build_runtime_catalogs(resolved))
    return resolved


def module_registry_from_app(app: Any) -> ModuleRegistry:
    """Return the module registry installed on a FastAPI application."""
    registry = getattr(app.state, _MODULE_REGISTRY_STATE_KEY, None)
    if not isinstance(registry, ModuleRegistry):
        raise RuntimeError("Module registry has not been installed on the FastAPI application")
    return registry


def module_registry_dependency(request: Request) -> ModuleRegistry:
    """FastAPI dependency exposing the installed module registry."""
    return module_registry_from_app(request.app)


def runtime_catalogs_from_app(app: Any) -> RuntimeCatalogs:
    """Return the RuntimeCatalogs installed on a FastAPI application."""
    catalogs = getattr(app.state, _RUNTIME_CATALOGS_STATE_KEY, None)
    if not isinstance(catalogs, RuntimeCatalogs):
        raise RuntimeError("RuntimeCatalogs have not been installed on the FastAPI application")
    return catalogs


def runtime_catalogs_dependency(request: Request) -> RuntimeCatalogs:
    """FastAPI dependency exposing the installed RuntimeCatalogs."""
    return runtime_catalogs_from_app(request.app)


@lru_cache(maxsize=1)
def get_module_registry() -> ModuleRegistry:
    return build_module_registry()


@lru_cache(maxsize=1)
def get_complete_module_registry() -> ModuleRegistry:
    """The complete-vocabulary registry, assembled once for the process.

    Cached for the same reason the active registry is: assembling it walks every ontology and diagram
    type, and read paths that need the full vocabulary are per-request.
    """
    return build_module_registry(complete_vocabulary=True)


@lru_cache(maxsize=1)
def complete_diagram_type_catalog() -> DiagramTypeCatalog:
    """Diagram-type lookup over the complete vocabulary.

    Which diagram types exist, and which of them project their content from a store instead of a
    repository file, is a fact about the software rather than about this host's configuration. A
    listing that asked the *active* registry would start including stale assurance diagram files the
    moment the confidential-store capability was gated off — the same reasoning that makes the
    assurance render path resolve its diagram type here.
    """
    return DiagramTypeCatalogImpl(build_module_catalog(get_complete_module_registry()))


def assurance_ontology_module() -> EdgeCatalogSource:
    """The statically loaded assurance ontology module — pure package
    configuration, independent of runtime capability enablement. Edge-matrix
    validation and the edge catalog read it directly; whether a transport
    surface is exposed at all is gated separately (registry enablement)."""
    return _assurance_module


_META_ONTOLOGY_ALIASES: dict[str, str] = {
    "archimate-4": "archimate-4-0",
    "sysml-v2": "sysml_v2_min",
}


def registered_meta_ontology_values(registry: ModuleRegistry) -> frozenset[str]:
    """Return meta-ontology aliases whose backing ontology modules are active."""
    return frozenset(
        alias for alias, module_name in _META_ONTOLOGY_ALIASES.items() if registry.find_ontology(module_name)
    )


def resolve_meta_ontology_artifact_types(
    meta_ontology: str, registry: ModuleRegistry
) -> frozenset[str] | None:
    """Return allowed artifact type names for a meta-ontology shortname, or None for no filter."""
    if not meta_ontology:
        return None
    module_name = _META_ONTOLOGY_ALIASES.get(meta_ontology)
    if not module_name:
        return frozenset()
    om = registry.find_ontology(module_name)
    return frozenset(om.entity_types.keys()) if om else frozenset()


def resolve_meta_ontology_module(meta_ontology: str, registry: ModuleRegistry) -> OntologyModule | None:
    """Return the registered OntologyModule backing a guidance/meta-ontology alias, or None
    if unknown or inactive. Used where a caller needs the full module (entity AND connection
    type vocabulary), not just the entity-type subset — e.g. arch-import-guidance key
    validation.

    Falls back to treating ``meta_ontology`` as a literal registered module name for aliases
    outside ``_META_ONTOLOGY_ALIASES`` (e.g. ``"assurance"``, whose module class is a
    separate concept from the architecture-framework meta-ontology picker that dict serves —
    it is not itself a selectable meta-ontology, but it can still carry its own guidance).
    """
    module_name = _META_ONTOLOGY_ALIASES.get(meta_ontology, meta_ontology)
    return registry.find_ontology(module_name)
