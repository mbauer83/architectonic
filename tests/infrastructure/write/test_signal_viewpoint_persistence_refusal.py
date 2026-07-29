"""D11 persistence refusal: applying a viewpoint that DECLARES a
security-signal source to a git-persisted diagram is refused with the
classification message — by semantics, never by whether values resolved. The
domain trigger and the write-path guard are both covered."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_criteria import EntityCriteriaGroup
from src.domain.viewpoints.viewpoint_derived_attribute_deferral import declares_signal_source
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointCatalog, ViewpointDefinition
from src.infrastructure.write.artifact_write.diagram import _refuse_signal_viewpoint_persistence

SIGNAL_DEFINITION = ViewpointDefinition(
    slug="security-posture", version=1, name="Security Posture",
    query=ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(),
        derived=(DerivedAttribute(name="max_cvss", source="security-signal",
                                  metric="max_cvss_score"),),
    ),
    presentation=None,
)
GRAPH_DEFINITION = ViewpointDefinition(
    slug="plain", version=1, name="Plain",
    query=ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(),
        derived=(DerivedAttribute(name="dependents"),),
    ),
    presentation=None,
)


class _Catalogs:
    def __init__(self) -> None:
        self.viewpoints = ViewpointCatalog(entries=(SIGNAL_DEFINITION, GRAPH_DEFINITION))


class _Verifier:
    _runtime_catalogs = _Catalogs()


class TestDomainTrigger:
    def test_signal_source_declaration_triggers(self) -> None:
        assert declares_signal_source(SIGNAL_DEFINITION) is True
        assert declares_signal_source(GRAPH_DEFINITION) is False

    def test_definition_without_query_never_triggers(self) -> None:
        bare = ViewpointDefinition(slug="s", version=1, name="s", query=None, presentation=None)
        assert declares_signal_source(bare) is False


class TestWritePathGuard:
    def test_applying_the_signal_viewpoint_is_refused_with_the_classification_message(self) -> None:
        with pytest.raises(ValueError, match="classification-bearing"):
            _refuse_signal_viewpoint_persistence(
                {"slug": "security-posture", "version": 1}, _Verifier(),  # type: ignore[arg-type]
            )

    def test_graph_viewpoints_and_absent_applications_pass(self) -> None:
        _refuse_signal_viewpoint_persistence({"slug": "plain", "version": 1}, _Verifier())  # type: ignore[arg-type]
        _refuse_signal_viewpoint_persistence(None, _Verifier())  # type: ignore[arg-type]
        _refuse_signal_viewpoint_persistence({}, _Verifier())  # type: ignore[arg-type]

    def test_unknown_slug_is_not_this_guards_concern(self) -> None:
        # Slug resolution/validation failures surface through the normal
        # viewpoint-application validation, not the signal guard.
        _refuse_signal_viewpoint_persistence({"slug": "missing", "version": 1}, _Verifier())  # type: ignore[arg-type]
