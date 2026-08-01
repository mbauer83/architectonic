"""Classification of every shipped entity type for relationship derivation."""

from __future__ import annotations

from src.domain.relationships.derivation_domains import derivation_domain
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module


def test_every_shipped_entity_type_has_the_expected_derivation_domain() -> None:
    module = load_archimate_4_module(_PACKAGE_DIR)
    expected = {
        "motivation": {
            "assessment",
            "driver",
            "goal",
            "meaning",
            "outcome",
            "principle",
            "requirement",
            "stakeholder",
            "value",
        },
        "strategy": {"capability", "course-of-action", "resource", "value-stream"},
        "implementation_migration": {"deliverable", "plateau", "work-package"},
        "relationships": {"and-junction", "or-junction"},
        "core": {
            "application-component",
            "application-interface",
            "artifact",
            "business-actor",
            "business-interface",
            "business-object",
            "collaboration",
            "communication-network",
            "data-object",
            "device",
            "distribution-network",
            "equipment",
            "event",
            "facility",
            "function",
            "global-artifact-reference",
            "grouping",
            "location",
            "material",
            "path",
            "process",
            "product",
            "role",
            "service",
            "system-software",
            "technology-interface",
            "technology-node",
        },
    }

    actual = {
        domain: {str(name) for name, info in module.entity_types.items() if derivation_domain(info) == domain}
        for domain in expected
    }

    assert actual == expected
