"""Unit tests proving verifier rule functions are pure and injectable.

WU-10: rules accept catalog parameters and are testable without any
filesystem access or global service locators.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.application.verification._verifier_rules_bindings import get_allowed_bindings
from src.application.verification._verifier_rules_diagram_references import check_diagram_references_scoped
from src.application.verification._verifier_rules_semantic import (
    _is_structure,
    _permitted,
    check_connection_semantics,
)
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.modules.catalogs import DiagramTypeCatalog

# ---------------------------------------------------------------------------
# Fake catalog stubs
# ---------------------------------------------------------------------------


class _FakeConnectionSemantics:
    """Minimal ConnectionSemantics that permits only 'archimate-association'."""

    def permissible_connection_types(self, source_type: str, target_type: str) -> list[str]:
        return ["archimate-association"]

    def is_symmetric(self, conn_type: str) -> bool:
        return False

    def permissible_target_types(self, source_type: str) -> dict[str, list[str]]:
        return {}

    def classify_connections(self, source_type: str) -> dict[str, dict[str, list[str]]]:
        return {}


class _FakeOntologyCatalog:
    """Minimal OntologyCatalog with controllable entity_types_with_class output."""

    def __init__(self, structure_types: frozenset[str] | None = None) -> None:
        self._structure_types = structure_types or frozenset()

    def entity_types_with_class(self, element_class: str) -> frozenset[str]:
        if element_class == "active-structure-element":
            return self._structure_types
        return frozenset()

    def all_entity_type_names(self) -> frozenset[str]:
        return frozenset(["requirement", "driver", "application-component"])

    def all_connection_type_names(self) -> frozenset[str]:
        return frozenset(["archimate-association", "archimate-realization"])

    def expand_entity_type_term(self, term: str) -> list[str]:
        return []

    def format_entity_type_term(self, term: str) -> str:
        return term

    def entity_type_term_matches(self, term: str, linked_types: set[str]) -> bool:
        return False

    # remaining Protocol stubs
    def all_entity_types(self):
        return {}

    def all_connection_types(self):
        return {}

    def known_domain_names(self):
        return frozenset()

    def domain_order(self):
        return []

    def domain_grouping(self):
        return {}

    def archimate_stereotype_to_connection_type(self):
        return {}

    def entity_type_prefixes(self):
        return {}

    def matrix_abbreviations_by_connection_type(self):
        return {}

    def matrix_connection_type_abbreviations(self):
        return {}


# ---------------------------------------------------------------------------
# _permitted — pure function
# ---------------------------------------------------------------------------


def test_permitted_allowed_returns_true():
    cat = _FakeConnectionSemantics()
    ok, alts = _permitted(cat, "application-component", "archimate-association", "requirement")
    assert ok is True
    assert alts == []


def test_permitted_disallowed_returns_false_with_alternatives():
    cat = _FakeConnectionSemantics()
    ok, alts = _permitted(cat, "application-component", "archimate-realization", "requirement")
    assert ok is False
    assert alts == ["archimate-association"]


# ---------------------------------------------------------------------------
# _is_structure — pure function
# ---------------------------------------------------------------------------


def test_is_structure_true_when_type_in_class():
    cat = _FakeOntologyCatalog(structure_types=frozenset(["application-component"]))
    assert _is_structure(cat, "application-component") is True


def test_is_structure_false_when_type_absent():
    cat = _FakeOntologyCatalog(structure_types=frozenset(["application-component"]))
    assert _is_structure(cat, "requirement") is False


# ---------------------------------------------------------------------------
# check_connection_semantics — skips gracefully when catalog=None
# ---------------------------------------------------------------------------


def _make_registry_stub(source_type: str, target_type: str) -> MagicMock:
    """Build a registry stub that returns consistent entity types."""
    registry = MagicMock()
    registry.find_file_by_id.return_value = None  # triggers early return in _entity_type
    return registry


def test_check_connection_semantics_skips_when_no_catalog(tmp_path: Path):
    result = VerificationResult(path=tmp_path / "x.md", file_type="connection")
    registry = MagicMock()
    check_connection_semantics(
        "SRC@1.abc.name", [("archimate-realization", "TGT@1.def.name")],
        registry, result, "loc",
        connections_catalog=None,
    )
    assert result.issues == []
    registry.find_file_by_id.assert_not_called()


def test_check_connection_semantics_runs_with_catalog(tmp_path: Path):
    """With an injected catalog the check executes (and skips when entity type not found)."""
    result = VerificationResult(path=tmp_path / "x.md", file_type="connection")
    registry = MagicMock()
    registry.find_file_by_id.return_value = None  # entity type lookup returns None → skip
    cat = _FakeConnectionSemantics()
    check_connection_semantics(
        "SRC@1.abc.name", [("archimate-realization", "TGT@1.def.name")],
        registry, result, "loc",
        connections_catalog=cat,
    )
    # source_type resolves to None (file not found) → issues list empty
    assert result.issues == []


# ---------------------------------------------------------------------------
# get_allowed_bindings — pure when catalog provided
# ---------------------------------------------------------------------------


def test_get_allowed_bindings_none_when_no_catalog():
    assert get_allowed_bindings("c4-container", None) is None


def test_get_allowed_bindings_none_for_empty_diagram_type():
    cat = MagicMock(spec=DiagramTypeCatalog)
    assert get_allowed_bindings("", cat) is None
    cat.find_diagram_type.assert_not_called()


def test_get_allowed_bindings_none_when_type_not_found():
    cat = MagicMock(spec=DiagramTypeCatalog)
    cat.find_diagram_type.return_value = None
    result = get_allowed_bindings("unknown-type", cat)
    assert result is None
    cat.find_diagram_type.assert_called_once_with("unknown-type")


# ---------------------------------------------------------------------------
# check_diagram_references_scoped — accepts diagram_type_catalog kwarg
# ---------------------------------------------------------------------------


def test_check_diagram_references_scoped_accepts_catalog_kwarg(tmp_path: Path):
    """Smoke test: function is callable with catalog kwarg, no globals needed."""
    registry = MagicMock()
    registry.entity_ids.return_value = set()
    registry.connection_ids.return_value = set()
    registry.enterprise_entity_ids.return_value = set()
    registry.enterprise_connection_ids.return_value = set()
    registry.entity_status.return_value = "draft"
    registry.connection_status.return_value = "draft"

    result = VerificationResult(path=tmp_path / "d.md", file_type="diagram")
    catalog = MagicMock(spec=DiagramTypeCatalog)
    catalog.find_diagram_type.return_value = None

    check_diagram_references_scoped(
        {"entity-ids-used": [], "connection-ids-used": []},
        registry, "engagement", result, "loc",
        diagram_type_catalog=catalog,
    )
    assert isinstance(result.issues, list)
