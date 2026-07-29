"""Tests for the 3 custom impact-analysis definitions shipped alongside the standard
Appendix-C library (``element-dependents``, ``element-dependencies``,
``process-technology-support``): transitive dependents/dependencies with certainty and
hops, cross-layer support with intermediate layers omitted, and MCP parameter-signature
surfacing. REST/MCP transport parity and generic-mechanism reconfiguration coverage live
in ``tests/tools/test_viewpoint_query_tool_impact_analysis.py``.
"""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_CATALOGS = build_runtime_catalogs(get_module_registry())
_REGISTRIES = build_registry_snapshot(_CATALOGS, [])


def _execute(slug: str, store: Store, **params: object):
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug=slug, parameters=params or None),
        catalog=_CATALOGS.viewpoints,
        read_access=store,
        registries=_REGISTRIES,
        index_generation=None,
        max_entities=500,
        default_limit=500,
        timeout_seconds=10.0,
    )


def _layered_store() -> Store:
    """A 4-hop, all-structural (archimate-assignment) chain spanning technology →
    application → business: node hosts a technology service, which hosts an application
    component, which realizes an application service, which supports a business process.
    All-structural composes transitively (DR2) across the full depth; a chain mixing
    dependency-role types (e.g. archimate-serving) does not compose past 3 hops under
    this ontology's rule table — a genuine rule-table property, not a fixture choice."""
    entities = {
        "ENT@process": entity(artifact_id="ENT@process", artifact_type="process", domain="business", name="Process"),
        "ENT@appsvc": entity(artifact_id="ENT@appsvc", artifact_type="service", domain="application", name="AppSvc"),
        "ENT@appcmp": entity(
            artifact_id="ENT@appcmp", artifact_type="application-component", domain="application", name="AppCmp"
        ),
        "ENT@techsvc": entity(artifact_id="ENT@techsvc", artifact_type="service", domain="technology", name="TechSvc"),
        "ENT@node": entity(
            artifact_id="ENT@node", artifact_type="technology-node", domain="technology", name="Node"
        ),
    }
    connections = [
        connection(artifact_id="CON@1", source="ENT@node", target="ENT@techsvc", conn_type="archimate-assignment"),
        connection(artifact_id="CON@2", source="ENT@techsvc", target="ENT@appcmp", conn_type="archimate-assignment"),
        connection(artifact_id="CON@3", source="ENT@appcmp", target="ENT@appsvc", conn_type="archimate-assignment"),
        connection(artifact_id="CON@4", source="ENT@appsvc", target="ENT@process", conn_type="archimate-assignment"),
    ]
    return Store(entities=entities, connections=connections)


class TestElementDependents:
    def test_returns_transitive_dependents_with_certainty_and_hops(self) -> None:
        # direction: incoming (locked shape) discovers entities upstream of the anchor via
        # *derived* (2+ hop composed) traversal only — include_connected's traversal:
        # derived deliberately excludes the immediate 1-hop neighbor (appsvc), since a
        # single link is a modeled connection, not a composition; a genuine property of
        # the locked shape (PLAN Appendix A Example 2 uses traversal: derived, not both,
        # on this inclusion), not a fixture artifact. Flagged in the report back.
        result = _execute("element-dependents", _layered_store(), anchor="ENT@process")
        assert set(result.entity_ids) == {"ENT@node", "ENT@techsvc", "ENT@appcmp", "ENT@process"}
        derived = [c for c in result.connections if c.certainty is not None]
        assert derived, "expected at least one derived dependent connection"
        assert all(c.certainty == "certain" for c in derived)
        assert all(c.hops is not None and c.hops >= 1 for c in derived)


class TestElementDependencies:
    def test_mirrors_dependents_outward(self) -> None:
        # direction: outgoing (the mirror); same 1-hop-neighbor exclusion as above.
        result = _execute("element-dependencies", _layered_store(), anchor="ENT@node")
        assert set(result.entity_ids) == {"ENT@node", "ENT@appcmp", "ENT@appsvc", "ENT@process"}


class TestProcessTechnologySupport:
    def test_returns_process_and_technology_only_no_application_layer(self) -> None:
        result = _execute("process-technology-support", _layered_store(), anchor="ENT@process")
        assert set(result.entity_ids) == {"ENT@process", "ENT@techsvc", "ENT@node"}
        assert "ENT@appsvc" not in result.entity_ids
        assert "ENT@appcmp" not in result.entity_ids

    def test_derived_support_connections_are_present(self) -> None:
        result = _execute("process-technology-support", _layered_store(), anchor="ENT@process")
        derived = [c for c in result.connections if c.certainty is not None]
        assert derived, "expected derived support connections"
        assert all(c.certainty == "certain" for c in derived)


class TestParameterSignatures:
    def test_all_three_custom_definitions_declare_a_required_anchor_parameter(self) -> None:
        for slug in ("element-dependents", "element-dependencies", "process-technology-support"):
            definition = _CATALOGS.viewpoints.get(slug)
            assert definition is not None and definition.query is not None
            parameters = definition.query.parameters
            assert len(parameters) == 1
            assert parameters[0].name == "anchor"
            assert parameters[0].value_type == "entity-id"
            assert parameters[0].required is True
