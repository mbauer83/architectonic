"""Tests for the heat-map style rule on ``resource-map``: the ``investment_level``
profile attribute (a repo-defined convention, present only when a repo's profile schema
declares it) drives a scale-mode ``node_color`` rule. Covers legend presence, correct
scale-position mapping, and graceful degradation (default style + a drift warning, never
an error) when a repo has not declared the attribute at all. ``capability-map``
deliberately ships NO heat rule — the strategy layer carries no investment attribute, and
a rule that can never resolve would be a standing unresolvable-outcome warning."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.application.viewpoints.repository_projection import project_repository
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA
from src.domain.viewpoints.viewpoint_scale_styling import ScaleStyleValue
from tests.application.viewpoints._fixtures import Store, connection, entity
from tests.domain.test_default_viewpoint_library import _CATALOGS, _REGISTRIES, _repo_root_with_fixture_profiles

_NO_PROFILE_REGISTRIES = build_registry_snapshot(_CATALOGS, [])


def _repo_root_with_shipped_defaults() -> Path:
    """A repo carrying exactly the SHIPPED default schemata (as the template's
    ensure pass writes them), proving the product defaults — not just test
    fixtures — make the heat-map resolve."""
    root = Path(tempfile.mkdtemp())
    schemata_dir = root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True)
    for filename, payload in DEFAULT_SCHEMATA.items():
        (schemata_dir / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return root


_SHIPPED_DEFAULT_REGISTRIES = build_registry_snapshot(_CATALOGS, [_repo_root_with_shipped_defaults()])


def _resource(artifact_id: str, investment_level: int | None) -> EntityRecord:
    extra: dict[str, object] = {} if investment_level is None else {"investment_level": investment_level}
    return entity(artifact_id=artifact_id, artifact_type="resource", domain="strategy", extra=extra)


class TestCapabilityMapShipsNoHeatRule:
    def test_capability_map_has_no_styling_rules_and_declares_its_targets(self) -> None:
        definition = _CATALOGS.viewpoints.get("capability-map")
        assert definition is not None
        assert definition.presentation is not None
        assert definition.presentation.styling_rules == ()
        assert definition.presentation.target_types == ("capability", "resource")

    def test_capability_map_execution_raises_no_style_warnings(self) -> None:
        definition = _CATALOGS.viewpoints.get("capability-map")
        assert definition is not None
        store = Store(
            entities={
                "ENT@c1": entity(artifact_id="ENT@c1", artifact_type="capability", domain="strategy"),
            }
        )
        projection = project_repository(definition, read_access=store, registries=_NO_PROFILE_REGISTRIES)
        assert projection.warnings == ()
        assert projection.rule_outcomes == ()


class TestHeatMapLegendAndScaling:
    def test_resource_map_projection_carries_a_heat_legend(self) -> None:
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={"ENT@r1": _resource("ENT@r1", 2)})
        projection = project_repository(definition, read_access=store, registries=_REGISTRIES)
        assert len(projection.scale_legends) == 1
        legend = projection.scale_legends[0]
        assert legend.capability == "node_color"
        assert legend.attribute == "investment_level"
        assert legend.tokens == ("heat-low", "heat-high")

    def test_low_and_high_investment_entities_scale_to_opposite_ends(self) -> None:
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={"ENT@low": _resource("ENT@low", 1), "ENT@high": _resource("ENT@high", 5)})
        projection = project_repository(definition, read_access=store, registries=_REGISTRIES)
        by_id = {item.item_id: item for item in projection.items}
        low_style = by_id["ENT@low"].style["node_color"]
        high_style = by_id["ENT@high"].style["node_color"]
        assert isinstance(low_style, ScaleStyleValue)
        assert isinstance(high_style, ScaleStyleValue)
        assert low_style.position == 0.0
        assert high_style.position == 1.0


class TestHeatMapResolvesWithShippedDefaultSchema:
    def test_shipped_resource_schema_makes_the_heat_map_scale_without_warnings(self) -> None:
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={"ENT@low": _resource("ENT@low", 1), "ENT@high": _resource("ENT@high", 5)})
        projection = project_repository(
            definition, read_access=store, registries=_SHIPPED_DEFAULT_REGISTRIES
        )
        assert projection.warnings == ()
        by_id = {item.item_id: item for item in projection.items}
        low_style = by_id["ENT@low"].style["node_color"]
        high_style = by_id["ENT@high"].style["node_color"]
        assert isinstance(low_style, ScaleStyleValue)
        assert isinstance(high_style, ScaleStyleValue)
        assert low_style.position == 0.0
        assert high_style.position == 1.0
        assert len(projection.scale_legends) == 1

    def test_mixed_population_with_connections_reports_no_drift(self) -> None:
        """A connection between populated entities must not make an entity-schema
        scale attribute look unresolvable — drift means resolvable NOWHERE."""
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(
            entities={
                "ENT@low": _resource("ENT@low", 1),
                "ENT@cap": entity(artifact_id="ENT@cap", artifact_type="capability", domain="strategy"),
            },
            connections=[
                connection(
                    artifact_id="CON@assign",
                    source="ENT@low",
                    target="ENT@cap",
                    conn_type="archimate-assignment",
                )
            ],
        )
        projection = project_repository(
            definition, read_access=store, registries=_SHIPPED_DEFAULT_REGISTRIES
        )
        assert projection.warnings == ()
        low_style = {item.item_id: item for item in projection.items}["ENT@low"].style["node_color"]
        assert isinstance(low_style, ScaleStyleValue)

    def test_properties_table_values_band_end_to_end(self, tmp_path: Path) -> None:
        """Live-shaped regression: values living in the entity's Properties TABLE
        (not fixture `extra`) must reach scale styling through the parser."""
        from src.application.artifacts.parsing import parse_entity

        model_root = tmp_path / "model"
        path = model_root / "strategy" / "resource" / "RES@1.abc.parsed-asset.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nartifact-id: RES@1.abc.parsed-asset\nartifact-type: resource\n"
            "name: Parsed Asset\nversion: 0.1.0\nstatus: active\n"
            "attribute-types:\n  investment_level: integer\n---\n\n"
            "<!-- §content -->\n\n## Parsed Asset\n\nBody.\n\n## Properties\n\n"
            "| Attribute | Value |\n|---|---|\n| investment_level | 5 |\n",
            encoding="utf-8",
        )
        record = parse_entity(
            path,
            model_root,
            domain_names=frozenset({"strategy", "motivation", "business", "application", "technology", "common"}),
        )
        assert record is not None
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={record.artifact_id: record, "ENT@low": _resource("ENT@low", 1)})
        projection = project_repository(
            definition, read_access=store, registries=_SHIPPED_DEFAULT_REGISTRIES
        )
        assert projection.warnings == ()
        style = {item.item_id: item for item in projection.items}[record.artifact_id].style["node_color"]
        assert isinstance(style, ScaleStyleValue)
        assert style.position == 1.0


class TestHeatMapAbsenceDegradesGracefully:
    def test_entity_missing_the_attribute_falls_back_to_default_style_not_a_crash(self) -> None:
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={"ENT@bare": _resource("ENT@bare", None)})
        projection = project_repository(definition, read_access=store, registries=_REGISTRIES)
        item = projection.items[0]
        assert "node_color" not in item.style or item.style.get("node_color") is None

    def test_repo_without_the_profile_attribute_declared_is_a_drift_warning_not_an_error(self) -> None:
        definition = _CATALOGS.viewpoints.get("resource-map")
        assert definition is not None
        store = Store(entities={"ENT@r1": _resource("ENT@r1", 4)})
        projection = project_repository(definition, read_access=store, registries=_NO_PROFILE_REGISTRIES)
        assert any("investment_level" in warning for warning in projection.warnings)
        item = projection.items[0]
        assert "node_color" not in item.style


def test_fixture_profile_repo_root_helper_is_reusable() -> None:
    """A sanity check that the shared fixture-profile installer this file imports from
    the base library test module still produces a root with both heat-map schemas."""
    root = _repo_root_with_fixture_profiles()
    assert (root / ".arch-repo" / "schemata" / "attributes.capability.schema.json").exists()
    assert (root / ".arch-repo" / "schemata" / "attributes.resource.schema.json").exists()
