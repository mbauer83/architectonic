"""Reader<->writer round-trip tests on synthetic documents (D10, WU-F2): every fixture
here is hand-authored, not derived from ``spec/c19c-examples/`` (the license rule forbids
copying that material into committed fixtures, verbatim or shaped).
"""

from __future__ import annotations

from src.application.exchange.document import (
    ExchangeElement,
    ExchangeModel,
    ExchangeProperty,
    ExchangePropertyDefinition,
    ExchangeRelationship,
    LangString,
)
from src.infrastructure.exchange.archimate_model_exchange import (
    ArchimateModelExchangeReader,
    ArchimateModelExchangeWriter,
)


def _round_trip(model: ExchangeModel) -> ExchangeModel:
    xml = ArchimateModelExchangeWriter().write(model)
    return ArchimateModelExchangeReader().read(xml)


class TestMinimalModel:
    def test_bare_model_round_trips(self) -> None:
        model = ExchangeModel(identifier="m1")
        assert _round_trip(model) == model


class TestElementsAndRelationships:
    def test_elements_and_a_relationship_round_trip(self) -> None:
        model = ExchangeModel(
            identifier="m1",
            names=(LangString("Widget Model", "en"),),
            elements=(
                ExchangeElement(identifier="e1", concept_type="BusinessActor", names=(LangString("Widget Corp"),)),
                ExchangeElement(identifier="e2", concept_type="BusinessRole", names=(LangString("Widget Maker"),)),
            ),
            relationships=(
                ExchangeRelationship(
                    identifier="r1", concept_type="Assignment", source="e1", target="e2",
                    names=(LangString("Assigns"),),
                ),
            ),
        )
        assert _round_trip(model) == model


class TestMultiLanguageNamesAndDocumentation:
    def test_several_names_and_documentation_entries_round_trip(self) -> None:
        model = ExchangeModel(
            identifier="m1",
            names=(LangString("English Name", "en"), LangString("Nom Francais", "fr")),
            documentation=(LangString("English doc", "en"),),
            elements=(
                ExchangeElement(
                    identifier="e1", concept_type="BusinessActor",
                    names=(LangString("A", "en"), LangString("B", "fr")),
                    documentation=(LangString("about A"),),
                ),
            ),
        )
        assert _round_trip(model) == model


class TestPropertiesAndPropertyDefinitions:
    def test_properties_on_model_and_elements_round_trip_with_definitions(self) -> None:
        model = ExchangeModel(
            identifier="m1",
            properties=(ExchangeProperty(property_definition_ref="pd2", values=(LangString("model-level value"),)),),
            elements=(
                ExchangeElement(
                    identifier="e1", concept_type="BusinessActor",
                    properties=(ExchangeProperty(property_definition_ref="pd1", values=(LangString("42"),)),),
                ),
            ),
            relationships=(
                ExchangeRelationship(
                    identifier="r1", concept_type="Assignment", source="e1", target="e1",
                    properties=(ExchangeProperty(property_definition_ref="pd1", values=(LangString("1"),)),),
                ),
            ),
            property_definitions=(
                ExchangePropertyDefinition(identifier="pd1", data_type="number", names=(LangString("Cost"),)),
                ExchangePropertyDefinition(identifier="pd2", data_type="string", names=(LangString("User Property"),)),
            ),
        )
        assert _round_trip(model) == model

    def test_a_property_with_multiple_values_round_trips(self) -> None:
        model = ExchangeModel(
            identifier="m1",
            elements=(
                ExchangeElement(
                    identifier="e1", concept_type="BusinessActor",
                    properties=(
                        ExchangeProperty(
                            property_definition_ref="pd1", values=(LangString("first"), LangString("second")),
                        ),
                    ),
                ),
            ),
        )
        assert _round_trip(model) == model


class TestEmptyCollections:
    def test_model_with_no_elements_or_relationships_round_trips(self) -> None:
        model = ExchangeModel(identifier="m1", names=(LangString("Empty Model"),))
        result = _round_trip(model)
        assert result == model
        assert result.elements == ()
        assert result.relationships == ()
        assert result.property_definitions == ()
