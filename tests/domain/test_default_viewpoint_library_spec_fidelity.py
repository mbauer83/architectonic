"""Spec-fidelity gate: every shipped Appendix-C definition's purpose/stakeholders/concerns/
scope element list matches its transcribed spec table exactly — an executable comparison,
not a review claim. "Core element" viewpoints (domain-union scope, no fixed element list
in the spec table) are asserted separately, without an element-list comparison."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_criteria import AttributeCondition
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.viewpoint_declarations import load_module_viewpoint_catalog
from src.ontologies.archimate_4._loader import _PACKAGE_DIR as _ARCH_PACKAGE_DIR
from tests.fixtures.viewpoints.standard_viewpoint_tables import STANDARD_VIEWPOINT_TABLES

_CATALOGS = build_runtime_catalogs(get_module_registry())
_DEFINITIONS_BY_SLUG = {d.slug: d for d in _CATALOGS.viewpoints.entries}

_CORE_ELEMENT_SLUGS = frozenset({"layered"})
# Custom, non-spec definitions shipped alongside the standard library — they have no
# ArchiMate spec table to compare against, so they're excluded here.
_CUSTOM_SLUGS = frozenset(
    {
        "element-dependents",
        "element-dependencies",
        "process-technology-support",
        "requirements-coverage-gaps",
        "component-traceability-gaps",
        "security-posture",
        "motivation-coverage",
    }
)
# The realization family deliberately deviates from the bare spec tables: each member
# assesses ONE target population (banded realized/unrealized) and includes its realizers
# as unbanded context, instead of rendering an undifferentiated type/domain dump. Their
# fidelity gate is the family-contract test below, not the spec element list.
_REALIZATION_FAMILY: dict[str, str] = {
    "goal-realization": "goal",
    "outcome-realization": "outcome",
    "requirements-realization": "requirement",
}


def test_every_table_has_a_shipped_definition() -> None:
    # Pure module-shipped catalog — `_DEFINITIONS_BY_SLUG` (built from the merged two-tier
    # catalog) is right for the per-slug lookups below, but an exact-membership assertion
    # must not be sensitive to whatever real engagement/enterprise content this
    # environment's configured workspace happens to have alongside the shipped library.
    shipped_only = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR)
    shipped = {d.slug for d in shipped_only.entries} - _CUSTOM_SLUGS
    tables = {table.slug for table in STANDARD_VIEWPOINT_TABLES}
    assert shipped == tables


def test_purpose_matches_the_spec_table_verbatim() -> None:
    for table in STANDARD_VIEWPOINT_TABLES:
        definition = _DEFINITIONS_BY_SLUG[table.slug]
        assert tuple(definition.purpose) == table.purpose, table.slug


def test_stakeholders_match_the_spec_table_verbatim() -> None:
    for table in STANDARD_VIEWPOINT_TABLES:
        definition = _DEFINITIONS_BY_SLUG[table.slug]
        assert tuple(definition.stakeholders) == table.stakeholders, table.slug


def test_concerns_match_the_spec_table_verbatim() -> None:
    for table in STANDARD_VIEWPOINT_TABLES:
        definition = _DEFINITIONS_BY_SLUG[table.slug]
        assert tuple(definition.concerns) == table.concerns, table.slug


def test_scope_element_list_matches_the_spec_table() -> None:
    for table in STANDARD_VIEWPOINT_TABLES:
        if table.slug in _CORE_ELEMENT_SLUGS or table.slug in _REALIZATION_FAMILY:
            continue
        definition = _DEFINITIONS_BY_SLUG[table.slug]
        scope_types = {str(t) for t in (definition.scope.entity_types or ())} - {
            "grouping", "and-junction", "or-junction",
        }
        assert scope_types == set(table.entity_types), table.slug


def test_core_element_viewpoints_have_no_fixed_scope_and_use_domain_union() -> None:
    for slug in _CORE_ELEMENT_SLUGS:
        definition = _DEFINITIONS_BY_SLUG[slug]
        assert definition.scope.entity_types is None
        assert definition.query is not None
        condition = definition.query.entity_criteria.children[0]
        assert isinstance(condition, AttributeCondition)
        assert condition.attribute == "domain"
        assert condition.comparator == "in"


def test_realization_family_upholds_the_target_and_banding_contract() -> None:
    """Per family member: the primary selection is exactly the assessed target type, that
    target population is declared for honest-empty messaging, realizers arrive via
    incoming-realization inclusions (direct AND derived), and realized/unrealized banding
    applies ONLY to the target type — contextual realizers are never banded."""
    for slug, target in _REALIZATION_FAMILY.items():
        definition = _DEFINITIONS_BY_SLUG[slug]
        assert definition.query is not None, slug
        condition = definition.query.entity_criteria.children[0]
        assert isinstance(condition, AttributeCondition), slug
        assert (condition.attribute, condition.comparator, condition.value.literal) == ("type", "eq", target), slug
        assert definition.presentation is not None, slug
        assert definition.presentation.target_types == (target,), slug
        inclusions = definition.query.include_connected
        assert {inclusion.traversal for inclusion in inclusions} == {"direct", "derived"}, slug
        assert all(inclusion.direction == "incoming" for inclusion in inclusions), slug
        rules = definition.presentation.styling_rules
        assert {rule.value for rule in rules} == {"positive", "critical"}, slug
        assert all(rule.applies_to == frozenset({target}) for rule in rules), slug
