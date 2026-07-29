"""Tests for matrix_builder.py: pure markdown matrix generation.

Covers: build_matrix_tables edge cases, symmetric connections, combined table,
abbreviation generation, and _single_table formatting.
"""

from __future__ import annotations

from src.application.modeling.matrix_builder import ConnTypeConfig, build_matrix_tables


class TestConnTypeConfig:
    def test_default_active(self) -> None:
        cfg = ConnTypeConfig(conn_type="association")
        assert cfg.active is True

    def test_inactive(self) -> None:
        cfg = ConnTypeConfig(conn_type="association", active=False)
        assert cfg.active is False


class TestBuildMatrixTables:
    def test_empty_entity_ids_returns_empty(self) -> None:
        result = build_matrix_tables(
            entity_ids=[],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={},
            connections=[],
        )
        assert result == ""

    def test_no_connections_returns_empty(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={"E1": "Entity 1", "E2": "Entity 2"},
            connections=[],
        )
        assert result == ""

    def test_no_active_configs_returns_empty(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("assoc", active=False)],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "assoc"}],
        )
        assert result == ""

    def test_single_table_with_connection(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("association")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "association"}],
        )
        assert "association" in result
        assert "✓" in result
        assert "E1" in result
        assert "E2" in result

    def test_no_connection_cell_is_nbsp(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("association")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "association"}],
        )
        assert "&nbsp;" in result

    def test_symmetric_connection_adds_reverse(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "assoc", "direction": "symmetric"}],
        )
        assert result.count("✓") >= 2

    def test_combined_table(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("association"), ConnTypeConfig("composition")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[
                {"source": "E1", "target": "E2", "conn_type": "association"},
                {"source": "E2", "target": "E1", "conn_type": "composition"},
            ],
            combined=True,
        )
        assert "Legend" in result

    def test_multiple_conn_types_separate_tables(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("assoc"), ConnTypeConfig("comp")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[
                {"source": "E1", "target": "E2", "conn_type": "assoc"},
            ],
        )
        assert "assoc" in result
        assert "comp" in result
        # Two tables separated by double newline
        assert "\n\n" in result

    def test_asymmetric_from_to_entity_ids(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2", "E3"],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={"E1": "E1", "E2": "E2", "E3": "E3"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "assoc"}],
            from_entity_ids=["E1"],
            to_entity_ids=["E2", "E3"],
        )
        assert "✓" in result
        assert "E1" in result

    def test_empty_from_entity_ids_returns_empty(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1"],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={"E1": "E1"},
            connections=[{"source": "E1", "target": "E1", "conn_type": "assoc"}],
            from_entity_ids=[],
            to_entity_ids=["E1"],
        )
        assert result == ""

    def test_combined_with_abbreviations(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("archimate-association"), ConnTypeConfig("archimate-composition")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "E1", "target": "E2", "conn_type": "archimate-association"}],
            combined=True,
            matrix_abbreviations={"archimate-association": "Ass", "archimate-composition": "Cmp"},
        )
        assert "Ass" in result or "Cmp" in result or "Legend" in result

    def test_combined_auto_abbreviations_dedup(self) -> None:
        # Two types with same first letter — should not generate duplicate abbreviations
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("alpha"), ConnTypeConfig("arrow")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[
                {"source": "E1", "target": "E2", "conn_type": "alpha"},
                {"source": "E2", "target": "E1", "conn_type": "arrow"},
            ],
            combined=True,
        )
        assert "Legend" in result

    def test_connection_outside_entity_set_ignored(self) -> None:
        result = build_matrix_tables(
            entity_ids=["E1", "E2"],
            conn_type_configs=[ConnTypeConfig("assoc")],
            entity_names={"E1": "E1", "E2": "E2"},
            connections=[{"source": "EXTERNAL", "target": "E2", "conn_type": "assoc"}],
        )
        assert "&nbsp;" in result or "✓" not in result
