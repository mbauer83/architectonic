"""Tests for concept-level specialization declarations."""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.specializations import (
    EndpointRestriction,
    RelationshipRestriction,
    SpecializationCatalog,
    specialization_catalog_from_mapping,
)


def test_parse_entity_and_connection_specializations() -> None:
    catalog = specialization_catalog_from_mapping(
        {
            "specializations": {
                "entity": {
                    "service": [
                        {
                            "slug": "business-service",
                            "name": "Business Service",
                            "description": "Externally visible business behavior.",
                            "notation": {"icon": "briefcase", "color": "#336699"},
                            "restrict_relationships": [
                                "archimate-serving",
                                {
                                    "connection_type": "archimate-realization",
                                    "source_type": "process",
                                    "target_type": "service",
                                },
                            ],
                            "attributes": {"criticality": {"type": "string"}},
                            "create_when": "Use for business-facing services.",
                            "never_create_when": "Do not use for implementation APIs.",
                        }
                    ]
                },
                "connection": {
                    "archimate-flow": [
                        {
                            "slug": "money-flow",
                            "name": "Money Flow",
                            "notation": {"line_style": "dashed", "label_marker": "$"},
                            "restrict_endpoints": [
                                {"source_types": ["business-actor"], "target_types": ["business-actor", "role"]}
                            ],
                        }
                    ]
                },
            }
        },
        module_alias="archimate-4",
    )

    entity = catalog.get("entity", "service", "business-service", module_alias="archimate-4")
    assert entity is not None
    assert entity.name == "Business Service"
    assert entity.notation.icon == "briefcase"
    assert entity.restrict_relationships == (
        RelationshipRestriction("archimate-serving"),
        RelationshipRestriction("archimate-realization", source_type="process", target_type="service"),
    )
    assert entity.attributes["criticality"] == {"type": "string"}

    connection = catalog.get("connection", "archimate-flow", "money-flow", module_alias="archimate-4")
    assert connection is not None
    assert connection.notation.line_style == "dashed"
    assert connection.restrict_endpoints == (
        EndpointRestriction(
            source_types=frozenset({"business-actor"}),
            target_types=frozenset({"business-actor", "role"}),
        ),
    )
    assert catalog.for_type("connection", "archimate-flow", module_alias="archimate-4") == (connection,)


def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate specialization"):
        specialization_catalog_from_mapping(
            {
                "specializations": {
                    "entity": {
                        "service": [
                            {"slug": "business-service", "name": "Business Service"},
                            {"slug": "business-service", "name": "Duplicate Business Service"},
                        ]
                    }
                }
            },
            module_alias="archimate-4",
        )


def test_lookup_without_module_alias_rejects_ambiguous_slug() -> None:
    left = specialization_catalog_from_mapping(
        {"specializations": {"entity": {"service": [{"slug": "contract", "name": "Contract"}]}}},
        module_alias="left",
    )
    right = specialization_catalog_from_mapping(
        {"specializations": {"entity": {"service": [{"slug": "contract", "name": "Contract"}]}}},
        module_alias="right",
    )
    catalog = SpecializationCatalog(left.entries + right.entries)

    with pytest.raises(ValueError, match="ambiguous"):
        catalog.get("entity", "service", "contract")

    assert catalog.get("entity", "service", "contract", module_alias="right") is not None


def test_restriction_narrowing_hook_reports_parent_broadening() -> None:
    catalog = specialization_catalog_from_mapping(
        {
            "specializations": {
                "entity": {
                    "service": [
                        {
                            "slug": "contract",
                            "name": "Contract",
                            "restrict_relationships": ["archimate-flow", "archimate-serving"],
                        }
                    ]
                },
                "connection": {
                    "archimate-flow": [
                        {
                            "slug": "money-flow",
                            "name": "Money Flow",
                            "restrict_endpoints": [
                                {"source": "business-actor", "target": "role"},
                                {"source": "technology-node", "target": "role"},
                            ],
                        }
                    ]
                },
            }
        },
        module_alias="archimate-4",
    )

    issues = catalog.validate_restriction_narrowing(
        parent_relationships={
            ("archimate-4", "service"): frozenset({RelationshipRestriction("archimate-serving")})
        },
        parent_endpoints={
            ("archimate-4", "archimate-flow"): frozenset(
                {
                    EndpointRestriction(
                        source_types=frozenset({"business-actor"}),
                        target_types=frozenset({"role"}),
                    )
                }
            )
        },
    )

    assert len(issues) == 2
    assert "restrict_relationships" in issues[0]
    assert "restrict_endpoints" in issues[1]


def test_restriction_narrowing_hook_accepts_subsets() -> None:
    catalog = specialization_catalog_from_mapping(
        {
            "specializations": {
                "entity": {
                    "service": [
                        {
                            "slug": "contract",
                            "name": "Contract",
                            "restrict_relationships": [
                                {
                                    "connection_type": "archimate-serving",
                                    "source_type": "process",
                                    "target_type": "service",
                                }
                            ],
                        }
                    ]
                },
                "connection": {
                    "archimate-flow": [
                        {
                            "slug": "money-flow",
                            "name": "Money Flow",
                            "restrict_endpoints": [{"source": "business-actor", "target": "role"}],
                        }
                    ]
                },
            }
        },
        module_alias="archimate-4",
    )

    issues = catalog.validate_restriction_narrowing(
        parent_relationships={
            ("archimate-4", "service"): frozenset(
                {
                    RelationshipRestriction(
                        "archimate-serving",
                        source_type="process",
                    )
                }
            )
        },
        parent_endpoints={
            ("archimate-4", "archimate-flow"): frozenset(
                {
                    EndpointRestriction(
                        source_types=frozenset({"business-actor", "role"}),
                        target_types=frozenset({"business-actor", "role"}),
                    )
                }
            )
        },
    )

    assert issues == ()
