"""Tests for the /api/modules registry discovery endpoint.

The route answers with an envelope — ``{"modules": [...]}`` — like every other collection read on this
surface. These read the list out of it rather than treating the response as one, which is also what a
client does.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
from src.infrastructure.rest.routers.modules import list_modules


@lru_cache(maxsize=1)
def _catalogs() -> RuntimeCatalogs:
    return build_runtime_catalogs(build_module_registry())


def _modules() -> list[dict[str, Any]]:
    response = list_modules(catalogs=_catalogs())
    modules = response["modules"]
    assert isinstance(modules, list)
    return modules


class TestModulesRoute:
    def test_returns_the_loaded_ontology_modules(self) -> None:
        assert len(_modules()) >= 1

    def test_the_list_arrives_under_the_envelope_key(self) -> None:
        """The envelope is the contract, not a wrapper the caller may look past: a bare array is what
        this used to serve, and nothing else on this surface answers that way."""
        assert set(list_modules(catalogs=_catalogs())) == {"modules"}

    def test_response_shape(self) -> None:
        for entry in _modules():
            assert "name" in entry
            assert "module_class" in entry
            assert "enabled" in entry
            assert "requires" in entry
            assert "entity_type_count" in entry
            assert "connection_type_count" in entry

    def test_module_class_is_non_empty_string(self) -> None:
        for entry in _modules():
            assert isinstance(entry["module_class"], str) and entry["module_class"], (
                f"Module {entry['name']!r} must have a non-empty module_class"
            )

    def test_registered_modules_appear_in_response(self) -> None:
        registry = build_module_registry()
        registered_names = set(registry.all_ontologies().keys())
        response_names = {entry["name"] for entry in _modules()}
        assert registered_names == response_names

    def test_entity_type_count_is_positive_for_real_modules(self) -> None:
        for entry in _modules():
            assert int(entry["entity_type_count"]) > 0, (
                f"Module {entry['name']!r} reported zero entity types"
            )

    def test_modules_are_name_ordered_so_two_reads_agree(self) -> None:
        """The catalog is a dict; without the sort a client diffing two reads of an unchanged registry
        would see a change."""
        names = [str(entry["name"]) for entry in _modules()]
        assert names == sorted(names)
