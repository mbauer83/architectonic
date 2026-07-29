"""``DeclarativeConceptMapper`` / ``exchange_mapping.yaml`` correctness (WU-F3a, D10 §4.5):
Appendix E.4 migration table coverage, the documented lossy cases, and specialization-hint
override behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.application.exchange.concept_mapping import UnmappableConceptError
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper

_XSD_PATH = Path(__file__).parents[4] / "spec" / "c19c-xsd" / "archimate3_Model.xsd"


def _xsd_enum_values(enum_name: str) -> list[str]:
    text = _XSD_PATH.read_text(encoding="utf-8")
    match = re.search(rf'<xs:simpleType name="{enum_name}">.*?</xs:simpleType>', text, re.S)
    assert match is not None
    return re.findall(r'value="([^"]+)"', match.group(0))


@pytest.fixture
def mapper() -> DeclarativeConceptMapper:
    return DeclarativeConceptMapper()


def test_unknown_element_type_is_unmappable(mapper: DeclarativeConceptMapper) -> None:
    with pytest.raises(UnmappableConceptError):
        mapper.element_to_archimate("NotARealType")


def test_unknown_relationship_type_is_unmappable(mapper: DeclarativeConceptMapper) -> None:
    with pytest.raises(UnmappableConceptError):
        mapper.relationship_to_archimate("NotARealType")


@pytest.mark.parametrize(
    ("concept_type", "expected_type", "expected_specialization"),
    [
        ("BusinessActor", "business-actor", None),
        ("BusinessService", "service", "business-service"),
        ("ApplicationService", "service", "application-service"),
        ("TechnologyService", "service", "technology-service"),
        ("BusinessProcess", "process", "business-process"),
        ("ApplicationFunction", "function", "application-function"),
        ("Contract", "business-object", "contract"),
        ("Representation", "business-object", "representation"),
        ("Constraint", "requirement", "constraint"),
        ("Gap", "assessment", "gap"),
        ("Node", "technology-node", None),
        ("AndJunction", "and-junction", None),
        ("OrJunction", "or-junction", None),
    ],
)
def test_element_migration_cases(
    mapper: DeclarativeConceptMapper, concept_type: str, expected_type: str, expected_specialization: str | None
) -> None:
    mapping = mapper.element_to_archimate(concept_type)
    assert mapping.archimate_type == expected_type
    assert mapping.specialization == expected_specialization
    assert mapping.warning is None


@pytest.mark.parametrize(
    "concept_type",
    ["BusinessInteraction", "ApplicationInteraction", "TechnologyInteraction", "ImplementationEvent"],
)
def test_lossy_element_cases_carry_a_warning(mapper: DeclarativeConceptMapper, concept_type: str) -> None:
    mapping = mapper.element_to_archimate(concept_type)
    assert mapping.warning is not None


def test_application_component_specialization_only_from_hint(mapper: DeclarativeConceptMapper) -> None:
    bare = mapper.element_to_archimate("ApplicationComponent")
    assert bare.archimate_type == "application-component"
    assert bare.specialization is None

    hinted = mapper.element_to_archimate("ApplicationComponent", specialization_hint="module")
    assert hinted.specialization == "module"


def test_assignment_specialization_only_from_hint(mapper: DeclarativeConceptMapper) -> None:
    bare = mapper.relationship_to_archimate("Assignment")
    assert bare.connection_type == "archimate-assignment"
    assert bare.specialization is None

    hinted = mapper.relationship_to_archimate("Assignment", specialization_hint="responsibility-assignment")
    assert hinted.specialization == "responsibility-assignment"


def test_composition_maps_to_composition_with_no_specialization(mapper: DeclarativeConceptMapper) -> None:
    mapping = mapper.relationship_to_archimate("Composition")
    assert mapping.connection_type == "archimate-composition"
    assert mapping.specialization is None
    assert mapping.warning is None


@pytest.mark.parametrize(
    ("concept_type", "expected_type"),
    [
        ("Composition", "archimate-composition"),
        ("Aggregation", "archimate-aggregation"),
        ("Assignment", "archimate-assignment"),
        ("Realization", "archimate-realization"),
        ("Serving", "archimate-serving"),
        ("Access", "archimate-access"),
        ("Influence", "archimate-influence"),
        ("Triggering", "archimate-triggering"),
        ("Flow", "archimate-flow"),
        ("Specialization", "archimate-specialization"),
        ("Association", "archimate-association"),
    ],
)
def test_all_relationship_types_covered(
    mapper: DeclarativeConceptMapper, concept_type: str, expected_type: str
) -> None:
    assert mapper.relationship_to_archimate(concept_type).connection_type == expected_type


# ── full-enum coverage against the real fetched XSD ────────────────────────────

pytestmark_skip_no_xsd = pytest.mark.skipif(not _XSD_PATH.exists(), reason="spec/c19c-xsd not fetched locally")


@pytestmark_skip_no_xsd
def test_every_xsd_element_type_maps(mapper: DeclarativeConceptMapper) -> None:
    for value in _xsd_enum_values("ElementTypeEnum"):
        mapper.element_to_archimate(value)  # raises UnmappableConceptError on any gap


@pytestmark_skip_no_xsd
def test_every_xsd_relationship_type_maps(mapper: DeclarativeConceptMapper) -> None:
    for value in _xsd_enum_values("RelationshipTypeEnum"):
        mapper.relationship_to_archimate(value)


def test_mapping_table_has_no_stray_rows_beyond_the_real_enum() -> None:
    if not _XSD_PATH.exists():
        pytest.skip("spec/c19c-xsd not fetched locally")
    mapping_path = (
        Path(__file__).parents[4]
        / "src" / "infrastructure" / "exchange" / "archimate_model_exchange" / "exchange_mapping.yaml"
    )
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    assert set(data["elements"]) == set(_xsd_enum_values("ElementTypeEnum"))
    assert set(data["relationships"]) == set(_xsd_enum_values("RelationshipTypeEnum"))
