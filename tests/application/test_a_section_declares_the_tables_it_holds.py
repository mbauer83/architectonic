"""A document type's section says which typed tables it holds, in the type's own schema file.

The declaration is held to two shapes that were not designed around it — a stress analysis and an
ATAM evaluation — and to the rule that a column is written as an attribute is: the cell schema a
column compiles to is the JSON Schema an attribute schema would state for the same property.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from src.application.artifacts.document_schema import normalize_document_schema
from src.application.artifacts.document_tables import (
    format_row_ids,
    row_ids_in,
    table_declarations,
)
from src.application.artifacts.schema import validate_against_schema
from src.domain.ontology_representation.property_value import SUPPORTED_SCHEMA_TYPES
from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS
from tests.support.typed_table_documents import (
    ARCHITECTURE_EVALUATION,
    EXAMPLE_TYPES,
    STRESS_ANALYSIS,
    document_type,
    raw_document_type,
    table_of,
)


def _one_table(**column: Any) -> list[dict[str, Any]]:
    """A section declaring one table with one column, the column being what is under test."""
    return [{"name": "Notes", "tables": [{"name": "notes", "row_id": "N", "columns": [{"name": "note"} | column]}]}]


class TestTheTwoExampleTypesAreExpressible:
    def test_a_stress_analysis_declares_its_five_tables(self) -> None:
        schema = document_type(STRESS_ANALYSIS)

        declared = {section.name: [table.name for table in section.tables] for section in schema.sections}
        assert declared == {
            "Naive Architecture": [],
            "Stressors": ["stressors"],
            "End States": ["end-states"],
            "Adaptations": ["adaptations"],
            "Incidence": ["incidence"],
            "Test": ["survival"],
        }

    def test_the_incidence_relation_is_rows_of_stressor_component_and_note(self) -> None:
        incidence = table_of(document_type(STRESS_ANALYSIS), "incidence")

        assert incidence.header == ("Id", "Stressor", "Component", "Note")
        assert [(column.kind, column.required) for column in incidence.columns] == [
            ("row", True),
            ("reference", True),
            ("value", False),
        ]
        assert incidence.column("stressor").row_table == "stressors"
        assert incidence.column("component").reference_terms == ("@active-structure-element",)

    def test_an_adaptation_names_its_candidate_architecture_as_plain_text(self) -> None:
        adaptations = table_of(document_type(STRESS_ANALYSIS), "adaptations")

        assert adaptations.column("candidate_architecture").cell_schema == {"type": "string"}
        assert adaptations.column("end_states").many

    def test_an_evaluation_declares_the_utility_tree_and_the_approach_analysis(self) -> None:
        schema = document_type(ARCHITECTURE_EVALUATION)

        assert table_of(schema, "utility").column("importance").cell_schema == {
            "type": "string",
            "enum": ["H", "M", "L"],
        }
        assert table_of(schema, "analysis").column("decision").reference_terms == ("doc:adr", "@all")
        assert table_of(schema, "analysis").column("nonrisk").title == "Non-risk"


class TestAColumnIsWrittenAsAnAttributeIs:
    @pytest.mark.parametrize("attribute_type", sorted(SUPPORTED_SCHEMA_TYPES))
    def test_every_attribute_type_is_a_column_type(self, attribute_type: str) -> None:
        ((table,),) = table_declarations("notes", _one_table(type=attribute_type))

        assert table.columns[0].cell_schema == {"type": attribute_type}

    def test_a_type_the_attribute_vocabulary_lacks_is_refused(self) -> None:
        with pytest.raises(ValueError, match="notes.*malformed table declaration"):
            table_declarations("notes", _one_table(type="date"))

    def test_json_schema_keywords_beside_the_type_reach_the_cell_schema_as_written(self) -> None:
        stated = {"type": "integer", "minimum": 1, "maximum": 5}

        ((table,),) = table_declarations("notes", _one_table(**stated))

        assert table.columns[0].cell_schema == stated

    def test_the_row_schema_is_the_one_the_products_validator_reads(self) -> None:
        stressors = table_of(document_type(STRESS_ANALYSIS), "stressors")

        assert stressors.row_schema["required"] == ["stressor", "set"]
        complete = {"stressor": "a", "set": "design", "plausible": True}
        assert validate_against_schema(complete, stressors.row_schema) == []
        assert validate_against_schema({"stressor": "a", "set": "neither"}, stressors.row_schema) == [
            "set: 'neither' is not one of ['design', 'test']"
        ]

    def test_a_column_that_addresses_something_reads_as_the_id_it_addresses(self) -> None:
        adaptations = table_of(document_type(STRESS_ANALYSIS), "adaptations")
        incidence = table_of(document_type(STRESS_ANALYSIS), "incidence")

        assert incidence.column("component").cell_schema == {"type": "string"}
        assert adaptations.column("end_states").cell_schema == {"type": "array", "items": {"type": "string"}}


class TestADeclarationThatCannotBeMeantIsRefused:
    @pytest.mark.parametrize(
        ("column", "says"),
        [
            ({"type": "reference"}, "column 'note': a reference column states `to`"),
            ({"type": "row"}, "column 'note': a row column states `table`"),
            ({"to": ["goal"]}, "`to` is a reference column's"),
            ({"type": "boolean", "table": "notes"}, "`table` is a row column's"),
            ({"type": "integer", "many": True}, "only a reference or a row column may be `many`"),
            ({"type": "reference", "to": []}, "to"),
            ({"title": " padded "}, "title"),
            ({"title": "two\nlines"}, "title"),
            ({"name": "Note"}, "name"),
        ],
    )
    def test_a_malformed_column_is_refused_naming_the_type_and_the_key(self, column: dict[str, Any], says: str) -> None:
        with pytest.raises(ValueError, match="notes") as refusal:
            table_declarations("notes", _one_table(**column))

        assert says in str(refusal.value)

    @pytest.mark.parametrize("missing", ["name", "row_id", "columns"])
    def test_a_table_states_its_name_its_row_id_and_its_columns(self, missing: str) -> None:
        sections = _one_table()
        del sections[0]["tables"][0][missing]

        with pytest.raises(ValueError, match=f"'{missing}' is a required property"):
            table_declarations("notes", sections)

    @pytest.mark.parametrize("prefix", ["s", "S1", "", "S-"])
    def test_a_row_id_prefix_is_letters_opening_with_a_capital(self, prefix: str) -> None:
        sections = _one_table()
        sections[0]["tables"][0]["row_id"] = prefix

        with pytest.raises(ValueError, match="row_id"):
            table_declarations("notes", sections)

    def test_a_row_column_names_a_table_the_type_declares(self) -> None:
        with pytest.raises(ValueError, match="takes rows of 'elsewhere', which this document type does not declare"):
            table_declarations("notes", _one_table(type="row", table="elsewhere"))

    @pytest.mark.parametrize(
        ("change", "says"),
        [
            ({"name": "stressors"}, "table name 'stressors' is declared more than once"),
            ({"row_id": "S"}, "row_id prefix 'S' is declared more than once"),
        ],
    )
    def test_two_tables_of_one_type_share_neither_a_name_nor_a_prefix(self, change: dict[str, str], says: str) -> None:
        raw = raw_document_type(STRESS_ANALYSIS)
        raw["sections"][2]["tables"][0] |= change

        with pytest.raises(ValueError, match=says):
            normalize_document_schema(STRESS_ANALYSIS, raw)

    def test_two_tables_of_one_section_are_headed_differently(self) -> None:
        sections = _one_table()
        sections[0]["tables"].append({"name": "more", "row_id": "M", "columns": [{"name": "note"}]})

        with pytest.raises(ValueError, match="both headed 'Id'"):
            table_declarations("notes", sections)

        sections[0]["tables"][1]["row_id_title"] = "More"
        assert [table.name for table in table_declarations("notes", sections)[0]] == ["notes", "more"]

    def test_two_columns_of_one_table_share_neither_a_name_nor_a_title(self) -> None:
        sections = _one_table()
        sections[0]["tables"][0]["columns"].append({"name": "remark", "title": "Note"})

        with pytest.raises(ValueError, match="two columns are titled 'Note'"):
            table_declarations("notes", sections)


class TestADeclarationSurvivesTheLoader:
    @pytest.mark.parametrize("doc_type", EXAMPLE_TYPES)
    def test_what_the_loader_serves_declares_the_same_tables(self, doc_type: str) -> None:
        """The loader normalises, serialises and normalises again; a table lost in between is lost."""
        schema = document_type(doc_type)

        assert normalize_document_schema(doc_type, schema.to_dict()).sections == schema.sections
        assert any(section.tables for section in schema.sections)

    @pytest.mark.parametrize("doc_type", sorted(BASE_DOCUMENT_SCHEMAS))
    def test_a_shipped_type_declares_none_and_serialises_as_it_did(self, doc_type: str) -> None:
        raw = copy.deepcopy(BASE_DOCUMENT_SCHEMAS[doc_type])
        schema = normalize_document_schema(doc_type, raw)

        assert all(section.tables == () for section in schema.sections)
        assert all("tables" not in section for section in schema.to_dict()["sections"])


class TestARowIdIsWrittenAndReadByItsTable:
    @pytest.mark.parametrize("number", [1, 9, 10, 1234])
    def test_the_number_a_row_id_was_written_from_reads_back(self, number: int) -> None:
        stressors = table_of(document_type(STRESS_ANALYSIS), "stressors")

        assert stressors.row_number(stressors.row_id(number)) == number

    @pytest.mark.parametrize("not_an_id", ["", "S", "S0", "S01", "s1", "S 1", "S1a", "E1", "1", "S-1"])
    def test_anything_else_is_no_row_id_of_the_table(self, not_an_id: str) -> None:
        assert table_of(document_type(STRESS_ANALYSIS), "stressors").row_number(not_an_id) is None

    def test_a_table_does_not_number_a_row_zero(self) -> None:
        with pytest.raises(ValueError, match="counts from one"):
            table_of(document_type(STRESS_ANALYSIS), "stressors").row_id(0)

    @pytest.mark.parametrize("row_ids", [("E1",), ("E1", "E2"), ("E10", "Risk3", "E2")])
    def test_several_row_ids_read_back_from_the_cell_they_were_written_to(self, row_ids: tuple[str, ...]) -> None:
        assert row_ids_in(format_row_ids(row_ids), many=True) == row_ids

    @pytest.mark.parametrize("text", ["E1,E2", "E1 ,  E2", " E1, E2 "])
    def test_spacing_around_the_separator_does_not_matter(self, text: str) -> None:
        assert row_ids_in(text, many=True) == ("E1", "E2")

    @pytest.mark.parametrize("text", ["E1, E2", "E1 E2", "the first one", "E1,", ""])
    def test_a_cell_of_one_row_id_holds_exactly_one(self, text: str) -> None:
        assert row_ids_in(text, many=False) is None
        assert row_ids_in("E1", many=False) == ("E1",)
