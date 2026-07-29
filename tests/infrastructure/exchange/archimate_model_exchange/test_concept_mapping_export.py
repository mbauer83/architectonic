"""``DeclarativeConceptMapper`` export (reverse) direction (WU-F3b, D10 §4.5): every
ArchiMate 4 type/specialization this repo ships resolves to a C19C concept type, preferring
a native (non-extension) mapping and falling back to a compatible-extension carrier only
when C19C genuinely has no native form.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.application.exchange.concept_mapping import UnmappableArchimateTypeError
from src.infrastructure.exchange.archimate_model_exchange.concept_mapping import DeclarativeConceptMapper

_ONTOLOGY_ROOT = Path(__file__).parents[4] / "src" / "ontologies" / "archimate_4"


@pytest.fixture
def mapper() -> DeclarativeConceptMapper:
    return DeclarativeConceptMapper()


# ── exact / native mappings ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("archimate_type", "specialization", "expected_concept_type"),
    [
        ("business-actor", None, "BusinessActor"),
        ("role", "business-role", "BusinessRole"),
        ("service", "business-service", "BusinessService"),
        ("service", "application-service", "ApplicationService"),
        ("service", "technology-service", "TechnologyService"),
        ("business-object", "contract", "Contract"),
        ("business-object", "representation", "Representation"),
        ("requirement", "constraint", "Constraint"),
        ("assessment", "gap", "Gap"),
        ("technology-node", None, "Node"),
        ("and-junction", None, "AndJunction"),
    ],
)
def test_native_element_mappings_carry_no_extension(
    mapper: DeclarativeConceptMapper, archimate_type: str, specialization: str | None, expected_concept_type: str
) -> None:
    mapping = mapper.element_to_exchange(archimate_type, specialization)
    assert mapping.concept_type == expected_concept_type
    assert mapping.extension_specialization is None


@pytest.mark.parametrize(
    ("connection_type", "expected_concept_type"),
    [
        ("archimate-composition", "Composition"),
        ("archimate-aggregation", "Aggregation"),
        ("archimate-realization", "Realization"),
        ("archimate-serving", "Serving"),
        ("archimate-access", "Access"),
        ("archimate-influence", "Influence"),
        ("archimate-triggering", "Triggering"),
        ("archimate-flow", "Flow"),
        ("archimate-specialization", "Specialization"),
        ("archimate-association", "Association"),
    ],
)
def test_native_relationship_mappings(
    mapper: DeclarativeConceptMapper, connection_type: str, expected_concept_type: str
) -> None:
    mapping = mapper.relationship_to_exchange(connection_type)
    assert mapping.concept_type == expected_concept_type
    assert mapping.extension_specialization is None


# ── compatible-extension fallbacks (no native 3.x form) ─────────────────────────


def test_application_component_specialization_carries_as_extension(mapper: DeclarativeConceptMapper) -> None:
    for specialization in ("service", "module", "endpoint"):
        mapping = mapper.element_to_exchange("application-component", specialization)
        assert mapping.concept_type == "ApplicationComponent"
        assert mapping.extension_specialization == specialization


def test_application_component_bare_is_native(mapper: DeclarativeConceptMapper) -> None:
    mapping = mapper.element_to_exchange("application-component")
    assert mapping.concept_type == "ApplicationComponent"
    assert mapping.extension_specialization is None


def test_assignment_specialization_carries_as_extension(mapper: DeclarativeConceptMapper) -> None:
    for specialization in ("responsibility-assignment", "behavior-assignment"):
        mapping = mapper.relationship_to_exchange("archimate-assignment", specialization)
        assert mapping.concept_type == "Assignment"
        assert mapping.extension_specialization == specialization


def test_application_role_falls_back_to_the_only_native_role_type(mapper: DeclarativeConceptMapper) -> None:
    # No 3.x ApplicationRole/TechnologyRole exists — BusinessRole is the sole native role
    # carrier, per the WU-F1 review's documented lossy case.
    for specialization in ("application-role", "technology-role"):
        mapping = mapper.element_to_exchange("role", specialization)
        assert mapping.concept_type == "BusinessRole"
        assert mapping.extension_specialization == specialization


# ── domain-hint fallback (layer-neutral type, no specialization) ───────────────


@pytest.mark.parametrize(
    ("domain_hint", "expected_concept_type"),
    [("business", "BusinessProcess"), ("application", "ApplicationProcess"), ("technology", "TechnologyProcess")],
)
def test_domain_hint_resolves_bare_layer_neutral_type(
    mapper: DeclarativeConceptMapper, domain_hint: str, expected_concept_type: str
) -> None:
    mapping = mapper.element_to_exchange("process", None, domain_hint=domain_hint)
    assert mapping.concept_type == expected_concept_type
    assert mapping.extension_specialization is None


def test_bare_layer_neutral_type_without_domain_hint_still_resolves_deterministically(
    mapper: DeclarativeConceptMapper,
) -> None:
    # No domain hint and no specialization: falls to the last-resort "any native
    # candidate" branch rather than raising — event's only bare-compatible carrier is
    # ImplementationEvent (round-trip-stable with the import-side lossy case).
    mapping = mapper.element_to_exchange("event", None)
    assert mapping.concept_type == "ImplementationEvent"


# ── unmappable (never expected, but must fail loudly not silently) ─────────────


def test_completely_unknown_archimate_type_raises(mapper: DeclarativeConceptMapper) -> None:
    with pytest.raises(UnmappableArchimateTypeError):
        mapper.element_to_exchange("not-a-real-archimate-type")


# ── full coverage against the shipped ontology ──────────────────────────────────


def _entity_types() -> list[str]:
    data = yaml.safe_load((_ONTOLOGY_ROOT / "entities.yaml").read_text(encoding="utf-8"))
    return list(data["entity_types"])


def _entity_specializations() -> dict[str, list[str]]:
    data = yaml.safe_load((_ONTOLOGY_ROOT / "specializations.yaml").read_text(encoding="utf-8"))
    return {
        base: [item["slug"] for item in items] for base, items in data["specializations"]["entity"].items()
    }


def _connection_specializations() -> dict[str, list[str]]:
    data = yaml.safe_load((_ONTOLOGY_ROOT / "specializations.yaml").read_text(encoding="utf-8"))
    return {
        base: [item["slug"] for item in items] for base, items in data["specializations"]["connection"].items()
    }


def _connection_types() -> list[str]:
    data = yaml.safe_load((_ONTOLOGY_ROOT / "connections.yaml").read_text(encoding="utf-8"))
    return list(data["connection_types"]["archimate"])


def test_every_shipped_entity_type_has_some_export_mapping(mapper: DeclarativeConceptMapper) -> None:
    for entity_type in _entity_types():
        if entity_type == "global-artifact-reference":
            continue  # internal type, never exchanged
        mapper.element_to_exchange(entity_type)  # raises on any real gap


def test_every_shipped_entity_specialization_has_some_export_mapping(mapper: DeclarativeConceptMapper) -> None:
    for base_type, slugs in _entity_specializations().items():
        for slug in slugs:
            mapper.element_to_exchange(base_type, slug)


def test_every_shipped_connection_type_has_some_export_mapping(mapper: DeclarativeConceptMapper) -> None:
    for connection_type in _connection_types():
        mapper.relationship_to_exchange(connection_type)


def test_every_shipped_connection_specialization_has_some_export_mapping(mapper: DeclarativeConceptMapper) -> None:
    for base_type, slugs in _connection_specializations().items():
        for slug in slugs:
            mapper.relationship_to_exchange(base_type, slug)
