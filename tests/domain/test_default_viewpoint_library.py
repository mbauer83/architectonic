"""Tests for the shipped Appendix-C default viewpoint library
(``src/ontologies/archimate_4/viewpoints.yaml``): every definition validates cleanly and
returns a non-empty population on a seeded fixture repo. Spec-fidelity comparison lives
in ``test_default_viewpoint_library_spec_fidelity.py``; the common-type-mapping proof
lives in ``test_default_viewpoint_library_common_types.py``.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.viewpoint_declarations import load_module_viewpoint_catalog
from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCH_PACKAGE_DIR
from tests.application.viewpoints._fixtures import Store, entity
from tests.fixtures.viewpoints.standard_viewpoint_tables import STANDARD_VIEWPOINT_TABLES

_CATALOGS = build_runtime_catalogs(get_module_registry())
_FIXTURE_SCHEMATA = Path(__file__).parents[1] / "fixtures" / "viewpoints" / "schemata"


def _repo_root_with_fixture_profiles() -> Path:
    """A throwaway repo root with every fixture profile installed (e.g.
    `investment_level` on capability/resource, for the heat-map style rules) — never
    cleaned up, since the process exits once tests finish."""
    root = Path(tempfile.mkdtemp())
    schemata_dir = root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True)
    for source in _FIXTURE_SCHEMATA.glob("*.schema.json"):
        shutil.copy(source, schemata_dir / source.name)
    return root


_REGISTRIES = build_registry_snapshot(_CATALOGS, [_repo_root_with_fixture_profiles()])
_KNOWN_SLUGS = {table.slug for table in STANDARD_VIEWPOINT_TABLES}

# One entity per ArchiMate type referenced anywhere in the library, unspecialized, domain
# matching the ontology's own hierarchy — proves every definition finds a real population
# without depending on any repo-specific authoring.
_DOMAIN_BY_TYPE = {
    name: info.hierarchy[0]
    for name, info in _CATALOGS.ontology.all_entity_types().items()
    if info.hierarchy and info.hierarchy[0] != "assurance"
}


def _seeded_store() -> Store:
    entities = {
        f"ENT@{type_slug}": entity(
            artifact_id=f"ENT@{type_slug}", artifact_type=type_slug, name=type_slug, domain=domain, subdomain=""
        )
        for type_slug, domain in _DOMAIN_BY_TYPE.items()
    }
    return Store(entities=entities)


_CUSTOM_SLUGS = {
    "element-dependents",
    "element-dependencies",
    "process-technology-support",
    "requirements-coverage-gaps",
    "component-traceability-gaps",
    "security-posture",
    "motivation-coverage",
}


def test_library_covers_the_25_standard_slugs_plus_the_custom_impact_analysis_set() -> None:
    # The pure module-shipped catalog, never merged with whatever real engagement/enterprise
    # content this environment's configured workspace happens to have — `_CATALOGS.viewpoints`
    # is the merged two-tier catalog (see `app_bootstrap._load_viewpoints`), which is right for
    # every other test in this module (they only care that shipped definitions behave, real
    # extra content alongside them is fine) but wrong for an exact-membership assertion.
    shipped_only = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR)
    slugs = {d.slug for d in shipped_only.entries}
    assert slugs == _KNOWN_SLUGS | _CUSTOM_SLUGS
    assert len(slugs) == 32
    # The custom slugs are this tool's own capability, never presented as part of the
    # ArchiMate standard's example set (see standard_viewpoint_tables.py, which only
    # transcribes the 25 spec-derived definitions).
    assert not (_CUSTOM_SLUGS & _KNOWN_SLUGS)


def test_every_definition_passes_save_mode_validation() -> None:
    for definition in _CATALOGS.viewpoints.entries:
        issues = validate_viewpoint_definition(
            definition,
            mode="save",
            known_entity_types=_REGISTRIES.known_entity_types,
            known_connection_types=_REGISTRIES.known_connection_types,
            known_specialization_slugs=_REGISTRIES.known_specialization_slugs,
            entity_attribute_types=dict(_REGISTRIES.entity_attribute_types),
            connection_attribute_types=dict(_REGISTRIES.connection_attribute_types),
            symmetric_connection_types=_REGISTRIES.symmetric_connection_types,
            depth_cap=_REGISTRIES.depth_cap,
            catalog=_CATALOGS.viewpoints,
        )
        assert issues == (), f"{definition.slug}: {issues}"


def test_every_standard_definition_returns_a_non_empty_population() -> None:
    """The standard definitions take no parameters; parameterised definitions require an
    anchor and are exercised separately in test_default_viewpoint_library_impact_analysis.py.

    Skip by "declares parameters" rather than a hardcoded slug set: `_CATALOGS.viewpoints`
    is the merged two-tier catalog, so it can contain engagement/enterprise-authored
    parameterised viewpoints beyond the module-shipped custom trio — those must be skipped
    here too, not just the known module slugs."""
    store = _seeded_store()
    for definition in _CATALOGS.viewpoints.entries:
        if definition.query is not None and definition.query.parameters:
            continue
        result = evaluate_viewpoint(
            ViewpointExecutionRequest(slug=definition.slug),
            catalog=_CATALOGS.viewpoints,
            read_access=store,
            registries=_REGISTRIES,
            index_generation=None,
            max_entities=500,
            default_limit=500,
            timeout_seconds=10.0,
        )
        assert result.entity_ids, f"{definition.slug}: empty population"
        assert result.query_summary
