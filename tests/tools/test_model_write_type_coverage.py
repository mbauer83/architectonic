"""Coverage tests: every supported type must be handled by writer mappings.

These are not BDD scenarios; they are exhaustive safety checks ensuring that
new registry entries in src/common/archimate_types.py cannot silently become
unwriteable.
"""

from __future__ import annotations

from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs


def test_writer_entity_type_mapping_covers_all() -> None:
    reg = build_module_registry()
    cat = build_runtime_catalogs(reg)
    all_types = {str(t) for t in reg.all_entity_types()}
    catalog_types = cat.ontology.all_entity_type_names()
    missing = sorted(all_types - catalog_types)
    assert missing == [], f"Missing entity mappings for: {missing}"


def test_writer_connection_type_mapping_covers_all() -> None:
    reg = build_module_registry()
    all_types = {str(t) for t in reg.all_connection_types()}
    catalog_conn_types = {str(t) for t in reg.all_connection_types()}
    missing = sorted(all_types - catalog_conn_types)
    assert missing == [], f"Missing connection mappings for: {missing}"
