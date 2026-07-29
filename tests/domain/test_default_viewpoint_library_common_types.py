"""Proves the common-type mapping rule (unqualified spec element names like "Process" or
"Service" map to this ontology's domain-neutral common slugs, with no `domain` filter):
a fixture repo whose processes/services/etc. carry no layer specialization is still
selected by viewpoints that scope on those common types, exactly as if they were
layer-specific — because they are not, by design."""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.viewpoint_declarations import load_module_viewpoint_catalog
from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCH_PACKAGE_DIR
from tests.application.viewpoints._fixtures import Store, entity

_CATALOGS = build_runtime_catalogs(get_module_registry())
_REGISTRIES = build_registry_snapshot(_CATALOGS, [])


def _unspecialized_store() -> Store:
    """Common-domain entities with no specialization set at all — proves the library
    does not silently rely on business-process/application-service etc. specializations
    that a real, unspecialized model may never carry."""
    def unspecialized(artifact_id: str, artifact_type: str):
        return entity(artifact_id=artifact_id, artifact_type=artifact_type, name=artifact_type, domain="common")

    entities = {
        "ENT@proc": unspecialized("ENT@proc", "process"),
        "ENT@svc": unspecialized("ENT@svc", "service"),
        "ENT@fnc": unspecialized("ENT@fnc", "function"),
        "ENT@evt": unspecialized("ENT@evt", "event"),
        "ENT@rol": unspecialized("ENT@rol", "role"),
        "ENT@col": unspecialized("ENT@col", "collaboration"),
    }
    return Store(entities=entities)


def _execute(slug: str, store: Store):
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug=slug),
        catalog=_CATALOGS.viewpoints,
        read_access=store,
        registries=_REGISTRIES,
        index_generation=None,
        max_entities=500,
        default_limit=500,
        timeout_seconds=10.0,
    )


def test_process_cooperation_selects_unspecialized_processes_and_services() -> None:
    result = _execute("process-cooperation", _unspecialized_store())
    assert "ENT@proc" in result.entity_ids
    assert "ENT@svc" in result.entity_ids
    assert "ENT@rol" in result.entity_ids
    assert "ENT@col" in result.entity_ids


def test_application_usage_selects_unspecialized_processes_and_services() -> None:
    result = _execute("application-usage", _unspecialized_store())
    assert "ENT@proc" in result.entity_ids
    assert "ENT@svc" in result.entity_ids


def test_technology_selects_unspecialized_common_behavior_elements() -> None:
    result = _execute("technology", _unspecialized_store())
    assert "ENT@proc" in result.entity_ids
    assert "ENT@fnc" in result.entity_ids
    assert "ENT@svc" in result.entity_ids
    assert "ENT@evt" in result.entity_ids


def test_no_common_type_scope_ever_uses_a_domain_condition_to_layer_scope() -> None:
    """Rule 2: a `domain: business`-style filter would silently exclude domain-neutral
    common entities entirely. No definition's query may condition on `domain` unless it
    is one of the explicit "Core element" (domain-union) viewpoints."""
    from src.domain.viewpoints.viewpoint_criteria import AttributeCondition

    # Pure module-shipped catalog: Rule 2 is a shipped-library authoring convention (never
    # layer-scope via a `domain` condition, since it would silently exclude domain-neutral
    # common entities) — it doesn't bind a real, user-authored engagement viewpoint that
    # may exist alongside the shipped library in this environment's configured workspace.
    shipped_only = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR)
    core_element_slugs = {"layered", "requirements-realization", "outcome-realization"}
    for definition in shipped_only.entries:
        if definition.slug in core_element_slugs or definition.query is None:
            continue
        for child in definition.query.entity_criteria.children:
            if isinstance(child, AttributeCondition):
                assert child.attribute != "domain", definition.slug
