"""Unit tests for the shared EntityFilter predicate (domain + entity-type + internal-type gate).

Used identically by /api/entity-display-search and /api/reference-search's entity branch —
the two routers share one predicate so their filtering semantics cannot drift.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.rest.routers._entity_filter import EntityFilter, parse_csv_filter

_ONTOLOGY = build_runtime_catalogs(get_module_registry()).ontology


def _entity(artifact_type: str = "requirement", domain: str = "motivation", artifact_id: str = "E1") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name="Entity",
        version="0.1.0",
        status="active",
        domain=domain,
        subdomain="",
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="Entity",
        display_alias="e1",
    )


def test_parse_csv_filter_splits_trims_and_drops_blanks() -> None:
    assert parse_csv_filter(" a, b ,,c") == frozenset({"a", "b", "c"})


def test_parse_csv_filter_lowercases_when_requested() -> None:
    assert parse_csv_filter("Application,Motivation", lowercase=True) == frozenset({"application", "motivation"})


def test_parse_csv_filter_empty_input_is_empty_set() -> None:
    assert parse_csv_filter(None) == frozenset()
    assert parse_csv_filter("") == frozenset()


def test_no_filters_matches_any_non_internal_entity() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types=None)
    assert entity_filter.matches(_entity(), ontology=_ONTOLOGY) is True


def test_internal_entity_type_never_matches() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types=None)
    internal = _entity(artifact_type="global-artifact-reference")
    assert entity_filter.matches(internal, ontology=_ONTOLOGY) is False


def test_domain_filter_excludes_non_matching_domain() -> None:
    entity_filter = EntityFilter.from_params(domains="application", entity_types=None)
    assert entity_filter.matches(_entity(domain="motivation"), ontology=_ONTOLOGY) is False
    assert entity_filter.matches(_entity(domain="application"), ontology=_ONTOLOGY) is True


def test_entity_type_filter_excludes_non_matching_type() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types="goal")
    assert entity_filter.matches(_entity(artifact_type="requirement"), ontology=_ONTOLOGY) is False
    assert entity_filter.matches(_entity(artifact_type="goal"), ontology=_ONTOLOGY) is True


def test_accepted_entity_types_is_an_additional_intersection() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types=None)
    entity = _entity(artifact_type="requirement")
    assert entity_filter.matches(entity, ontology=_ONTOLOGY, accepted_entity_types=frozenset({"requirement"})) is True
    assert entity_filter.matches(entity, ontology=_ONTOLOGY, accepted_entity_types=frozenset({"goal"})) is False


def test_keyword_facet_requires_every_requested_keyword() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types=None, keywords="wizard-draft")
    tagged = replace(_entity(artifact_id="E-tagged"), keywords=("wizard-draft", "other"))
    untagged = _entity(artifact_id="E-untagged")
    assert entity_filter.matches(tagged, ontology=_ONTOLOGY) is True
    assert entity_filter.matches(untagged, ontology=_ONTOLOGY) is False


def test_keyword_facet_defaults_to_empty_and_matches_all() -> None:
    entity_filter = EntityFilter.from_params(domains=None, entity_types=None)
    assert entity_filter.keywords == frozenset()
    assert entity_filter.matches(_entity(), ontology=_ONTOLOGY) is True
