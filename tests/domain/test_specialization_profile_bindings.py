"""WU-P2: a specialization may bind named profiles by name, in declaration order.

The binding is stored on the specialization here; resolving it into the effective schema
is WU-P3, and rejecting an undefined name is WU-Q1. These tests only assert the parse.
"""

from __future__ import annotations

from src.domain.ontology_representation.specializations import specialization_catalog_from_mapping


def _catalog(*items: dict[str, object]):
    return specialization_catalog_from_mapping(
        {"specializations": {"entity": {"application-component": list(items)}}},
        module_alias="archimate-4",
    )


def _get(catalog, slug: str):
    return catalog.get("entity", "application-component", slug, module_alias="archimate-4")


def test_absent_binding_is_empty() -> None:
    catalog = _catalog({"slug": "service"})
    assert _get(catalog, "service").bound_profiles == ()


def test_single_binding() -> None:
    catalog = _catalog({"slug": "service", "profiles": ["supplier-info"]})
    assert _get(catalog, "service").bound_profiles == ("supplier-info",)


def test_multiple_bindings_keep_declaration_order() -> None:
    catalog = _catalog({"slug": "service", "profiles": ["b-profile", "a-profile", "c-profile"]})
    assert _get(catalog, "service").bound_profiles == ("b-profile", "a-profile", "c-profile")


def test_repeated_binding_is_deduplicated() -> None:
    catalog = _catalog({"slug": "service", "profiles": ["p", "p", "q"]})
    assert _get(catalog, "service").bound_profiles == ("p", "q")


def test_same_profile_bound_by_several_specializations_contributes_to_each() -> None:
    catalog = _catalog(
        {"slug": "service", "profiles": ["shared"]},
        {"slug": "module", "profiles": ["shared", "module-only"]},
    )
    assert _get(catalog, "service").bound_profiles == ("shared",)
    assert _get(catalog, "module").bound_profiles == ("shared", "module-only")


def test_non_list_binding_yields_no_bindings() -> None:
    catalog = _catalog({"slug": "service", "profiles": "not-a-list"})
    assert _get(catalog, "service").bound_profiles == ()
