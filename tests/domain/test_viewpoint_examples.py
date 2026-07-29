"""Representative viewpoint declarations parse, round-trip, and validate.

The profile fixtures are installed into a temporary repository so validation exercises the
normal attribute-schema loading path. Removing a fixture profile must make its declaration
fail validation.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.application.artifact_schema import load_attribute_schema
from src.domain.viewpoints.viewpoint_parsing import viewpoint_catalog_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_catalog_to_mapping
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.ontologies.archimate_4._loader import load_archimate_4_module

_ARCHIMATE_PACKAGE_DIR = Path(__file__).parents[2] / "src" / "ontologies" / "archimate_4"
_FIXTURE_SCHEMATA = Path(__file__).parents[1] / "fixtures" / "viewpoints" / "schemata"

_EXAMPLES_YAML = (Path(__file__).parents[1] / "fixtures" / "viewpoints" / "viewpoint_examples.yaml").read_text()


def _flat_attribute_types(schema: dict[str, object] | None) -> dict[str, str]:
    if schema is None:
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {str(name): str(spec.get("type", "")) for name, spec in properties.items() if isinstance(spec, dict)}


@pytest.fixture
def repo_with_fixture_profiles(tmp_path: Path) -> Path:
    schemata_dir = tmp_path / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True)
    for source in _FIXTURE_SCHEMATA.glob("*.schema.json"):
        shutil.copy(source, schemata_dir / source.name)
    return tmp_path


def _registries(repo_root: Path) -> dict[str, object]:
    module = load_archimate_4_module(_ARCHIMATE_PACKAGE_DIR)
    entity_types: dict[str, str] = {}
    for artifact_type in ("application-component", "process"):
        entity_types.update(_flat_attribute_types(load_attribute_schema(repo_root, artifact_type)))
    connection_types = _flat_attribute_types(load_attribute_schema(repo_root, "archimate-serving"))
    return {
        "known_entity_types": frozenset(str(t) for t in module.entity_types),
        "known_connection_types": frozenset(str(t) for t in module.connection_types),
        "known_specialization_slugs": frozenset({"business-process"}),
        "entity_attribute_types": entity_types,
        "connection_attribute_types": connection_types,
    }


class TestViewpointExamples:
    def test_every_example_parses_and_round_trips(self) -> None:
        data = yaml.safe_load(_EXAMPLES_YAML)
        catalog = viewpoint_catalog_from_mapping(data)
        assert len(catalog.entries) == 5
        reparsed = viewpoint_catalog_from_mapping(viewpoint_catalog_to_mapping(catalog))
        assert reparsed == catalog

    def test_every_example_passes_save_mode_validation(self, repo_with_fixture_profiles: Path) -> None:
        data = yaml.safe_load(_EXAMPLES_YAML)
        catalog = viewpoint_catalog_from_mapping(data)
        registries = _registries(repo_with_fixture_profiles)
        for definition in catalog.entries:
            issues = validate_viewpoint_definition(definition, mode="save", **registries)  # type: ignore[arg-type]
            errors = [i for i in issues if i.severity == "error"]
            assert errors == [], f"{definition.slug}: {errors}"

    def test_removing_a_fixture_profile_makes_an_example_fail(self, repo_with_fixture_profiles: Path) -> None:
        (
            repo_with_fixture_profiles / ".arch-repo" / "schemata" / "attributes.application-component.schema.json"
        ).unlink()
        data = yaml.safe_load(_EXAMPLES_YAML)
        catalog = viewpoint_catalog_from_mapping(data)
        definition = catalog.get("component-lifecycle-table")
        assert definition is not None
        registries = _registries(repo_with_fixture_profiles)
        issues = validate_viewpoint_definition(definition, mode="save", **registries)  # type: ignore[arg-type]
        errors = [i for i in issues if i.severity == "error" and i.code == "unknown-attribute"]
        assert errors, "expected an unknown-attribute error once risk_score's profile is removed"
