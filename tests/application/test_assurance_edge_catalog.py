"""Edge-catalog contract: the payload equals the loaded module's representation
(types, matrix, reference catalog) — compared against module data structures,
never against YAML bytes — and the per-pair legal-set callable mirrors the
matrix exactly."""

from __future__ import annotations

from src.application.assurance_edge_catalog import build_edge_catalog, legal_connection_types_for
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.ontologies.assurance._loader import _PACKAGE_DIR, load_assurance_module

_MODULE = load_assurance_module(_PACKAGE_DIR)
_CATALOG = build_edge_catalog(_MODULE)


class TestEdgeTypes:
    def test_edge_types_equal_module_connection_types(self) -> None:
        assert [t["name"] for t in _CATALOG["edge_types"]] == sorted(
            str(name) for name in _MODULE.connection_types
        )

    def test_edge_labels_come_from_the_module(self) -> None:
        by_name = {t["name"]: t["label"] for t in _CATALOG["edge_types"]}
        for name, info in _MODULE.connection_types.items():
            assert by_name[str(name)] == info.conn_lang


class TestPermittedMatrix:
    def test_rows_reconstruct_the_module_matrix_exactly(self) -> None:
        reconstructed = {
            (row["source_type"], row["target_type"], conn)
            for row in _CATALOG["permitted"]
            for conn in row["connection_types"]
        }
        module_rules = {
            (str(source), str(target), str(conn))
            for source, entries in _MODULE.permitted_relationships.by_source().items()
            for target, conn in entries
        }
        assert reconstructed == module_rules

    def test_every_edge_type_appears_in_at_least_one_row(self) -> None:
        used = {conn for row in _CATALOG["permitted"] for conn in row["connection_types"]}
        assert used == {t["name"] for t in _CATALOG["edge_types"]}


class TestReferenceTypes:
    def test_reference_types_equal_module_catalog(self) -> None:
        assert {r["name"]: r["description"] for r in _CATALOG["reference_types"]} \
            == _MODULE.reference_types

    def test_reference_and_edge_types_are_disjoint(self) -> None:
        edge_names = {t["name"] for t in _CATALOG["edge_types"]}
        ref_names = {r["name"] for r in _CATALOG["reference_types"]}
        assert edge_names & ref_names == set()


class TestLegalSetCallable:
    def test_mirrors_the_matrix_for_a_known_pair(self) -> None:
        legal = legal_connection_types_for(_MODULE)
        expected = {
            str(conn) for conn in _MODULE.permitted_relationships.permitted_connection_types(
                EntityTypeName("hazard"), EntityTypeName("loss"),
            )
        }
        assert expected  # the STPA chain pair must be legal
        assert legal("hazard", "loss") == frozenset(expected)

    def test_unknown_pair_is_empty(self) -> None:
        legal = legal_connection_types_for(_MODULE)
        assert legal("no-such-type", "loss") == frozenset()

    def test_agrees_with_permits_on_every_matrix_row(self) -> None:
        legal = legal_connection_types_for(_MODULE)
        for source, entries in _MODULE.permitted_relationships.by_source().items():
            for target, conn in entries:
                assert str(conn) in legal(str(source), str(target))
                assert _MODULE.permitted_relationships.permits(
                    EntityTypeName(str(source)), EntityTypeName(str(target)),
                    ConnectionTypeName(str(conn)),
                )
