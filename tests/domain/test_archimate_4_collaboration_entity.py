"""The Collaboration entity type (ArchiMate 4 spec §4.1.2): a Common-domain internal
active-structure element, previously missing from this module entirely (found during the
WU-C2 Appendix B recheck)."""

from __future__ import annotations

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module


def test_collaboration_entity_type_exists_with_expected_classes() -> None:
    module = load_archimate_4_module(_PACKAGE_DIR)
    collaboration = module.entity_types[EntityTypeName("collaboration")]

    assert "active-structure-element" in collaboration.classes
    assert "internal-active-structure-element" in collaboration.classes


def test_collaboration_may_aggregate_and_compose_interfaces() -> None:
    """"A collaboration may aggregate interfaces that it provides to its environment" (§4.1.2)."""
    module = load_archimate_4_module(_PACKAGE_DIR)
    rules = module.permitted_relationships

    for interface in ("business-interface", "application-interface", "technology-interface"):
        for conn in ("archimate-aggregation", "archimate-composition"):
            assert rules.permits(
                EntityTypeName("collaboration"), EntityTypeName(interface), ConnectionTypeName(conn)
            )


def test_collaboration_may_be_assigned_to_functions_and_processes() -> None:
    """"A collaboration may be assigned to one or more processes or functions" (§4.1.2)."""
    module = load_archimate_4_module(_PACKAGE_DIR)
    rules = module.permitted_relationships

    for behavior in ("function", "process"):
        assert rules.permits(
            EntityTypeName("collaboration"), EntityTypeName(behavior), ConnectionTypeName("archimate-assignment")
        )
