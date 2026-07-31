"""The catalog contracts, held against the code that produces them.

Same guard as the assurance aggregates, for the four reads that describe the repository rather than
anything in it. Two of them are worth guarding for a reason beyond drift:

``/api/stats`` is served through a *port* whose return type is ``dict[str, object]`` — the merge in
``_combined_lookup`` is deliberately shape-blind, so it composes any two stat maps and the type system
has nothing to check. One concrete implementation decides the shape; this is what ties the contract to
it, and what would fail if a second implementation disagreed.

``/api/modules`` reads its fields off the ontology-module object with ``getattr`` defaults, so a renamed
attribute would silently start serving a default instead of failing.
"""

from __future__ import annotations

import ast
import pathlib

from src.infrastructure.gui.contracts.catalog import (
    BackendIdentityResponse,
    EntityTaxonomyResponse,
    LoadedModuleListResponse,
    LoadedModuleResponse,
    RepositoryStatsResponse,
    TaxonomyDomainResponse,
    TaxonomyTypeResponse,
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "src" / "infrastructure" / "artifact_index" / "service.py"
_ROUTERS = _ROOT / "src" / "infrastructure" / "gui" / "routers"


def _function(path: pathlib.Path, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name} — the producer moved or was renamed")


def _keys(node: ast.Dict) -> frozenset[str]:
    return frozenset(
        k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
    )


def _dict_literals(path: pathlib.Path, name: str) -> list[frozenset[str]]:
    return [_keys(n) for n in ast.walk(_function(path, name)) if isinstance(n, ast.Dict)]


def _returned_keys(path: pathlib.Path, name: str) -> frozenset[str]:
    for node in ast.walk(_function(path, name)):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return _keys(node.value)
    raise AssertionError(f"{name} no longer returns a dict literal")


def _fields(model: type) -> set[str]:
    return set(model.model_fields)  # type: ignore[attr-defined]


def test_the_stats_contract_matches_the_index_that_computes_it() -> None:
    """The port promises only ``dict[str, object]``; this is what pins the shape to its producer."""
    assert _returned_keys(_INDEX, "stats") == _fields(RepositoryStatsResponse)


def test_the_combining_lookup_adds_no_key_of_its_own() -> None:
    """A repository served as engagement-plus-enterprise merges two stat maps key by key. If the merge
    ever synthesised a key, the served shape would differ from the single-repository one and only one of
    the two could match the contract."""
    source = (_ROOT / "src" / "infrastructure" / "artifact_index" / "_combined_lookup.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "stats":
            literals = [n for n in ast.walk(node) if isinstance(n, ast.Dict) and n.keys]
            assert not literals, "the combining stats() now builds keys of its own"
            return
    raise AssertionError("_combined_lookup.stats not found")


def test_the_identity_contract_matches_what_the_route_returns() -> None:
    assert _returned_keys(_ROUTERS / "entities.py", "get_backend_identity") == _fields(
        BackendIdentityResponse
    )


def test_the_module_envelope_and_its_rows_match_what_the_route_builds() -> None:
    """The row's fields come from ``getattr`` with defaults, so a renamed attribute serves a default
    rather than failing. A key set comparison is what still notices."""
    literals = [keys for keys in _dict_literals(_ROUTERS / "modules.py", "list_modules") if keys]
    assert frozenset(_fields(LoadedModuleListResponse)) in literals
    assert frozenset(_fields(LoadedModuleResponse)) in literals


def test_the_taxonomy_shapes_match_what_the_route_builds() -> None:
    literals = _dict_literals(_ROUTERS / "entity_search.py", "get_entity_taxonomy")
    assert _returned_keys(_ROUTERS / "entity_search.py", "get_entity_taxonomy") == _fields(
        EntityTaxonomyResponse
    )
    assert frozenset(_fields(TaxonomyTypeResponse)) in literals
    assert frozenset(_fields(TaxonomyDomainResponse)) in literals
