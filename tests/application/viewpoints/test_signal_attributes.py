"""Signal-derived viewpoint attributes (D10): partitioned out of the pure
graph evaluator, batch-fetched (criteria-referenced over the full scoped
population; presentation-only over the retained population, ONE call),
unavailable → explicit warning + default styling (never mixed values), and
the null capability for deployments without assurance."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.viewpoints.evaluate_viewpoint import (
    ViewpointExecutionRequest,
    evaluate_viewpoint,
    project_viewpoint_repository,
)
from src.application.viewpoints.ports import NullSignalAttributeCapability, SignalMetricsBatch
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES, Store, entity

_DEFAULTS: dict[str, object] = dict(
    max_entities=500, default_limit=500, timeout_seconds=10.0, index_generation=None,
)

SIGNAL_ATTR = DerivedAttribute(
    name="open_vulns", source="security-signal", metric="distinct_open_vulnerabilities",
)


class RecordingCapability:
    def __init__(self, values: dict[tuple[str, str], object] | None = None,
                 *, available: bool = True, note: str | None = None) -> None:
        self._values = values or {}
        self._available = available
        self._note = note
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def fetch_metrics(self, entity_ids: Sequence[str], metric_names: Sequence[str]) -> SignalMetricsBatch:
        self.calls.append((tuple(entity_ids), tuple(metric_names)))
        if not self._available:
            return SignalMetricsBatch(available=False, note=self._note)
        return SignalMetricsBatch(available=True, values=self._values)


def _store() -> Store:
    records = [
        entity(artifact_id="APP@1.aa.one", artifact_type="application-component"),
        entity(artifact_id="APP@2.bb.two", artifact_type="application-component"),
        entity(artifact_id="GOL@3.cc.goal", artifact_type="goal", domain="motivation"),
    ]
    return Store(entities={record.artifact_id: record for record in records})


def _catalog(query: ExecutableViewpointQuery, presentation: PresentationSpec | None = None) -> ViewpointCatalog:
    return ViewpointCatalog(entries=(
        ViewpointDefinition(slug="vp", version=1, name="vp", query=query, presentation=presentation),
    ))


def _run(query: ExecutableViewpointQuery, capability: object, presentation: PresentationSpec | None = None):
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug="vp"),
        catalog=_catalog(query, presentation),
        read_access=_store(),
        registries=REGISTRIES,
        signal_capability=capability,  # type: ignore[arg-type]
        **_DEFAULTS,  # type: ignore[arg-type]
    )


class TestCriteriaReferencedSignalAttributes:
    QUERY = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(children=(
            AttributeCondition(attribute="derived.open_vulns", comparator="gt", value=ValueRef(literal=0)),
        )),
        derived=(SIGNAL_ATTR,),
    )

    def test_membership_follows_fetched_values_one_batch_over_full_population(self) -> None:
        capability = RecordingCapability({
            ("APP@1.aa.one", "distinct_open_vulnerabilities"): 3,
            ("APP@2.bb.two", "distinct_open_vulnerabilities"): 0,
        })
        result = _run(self.QUERY, capability)
        ids = [item.id for item in result.entities]
        assert ids == ["APP@1.aa.one"]
        assert len(capability.calls) == 1
        called_ids, called_metrics = capability.calls[0]
        assert set(called_ids) == {"APP@1.aa.one", "APP@2.bb.two", "GOL@3.cc.goal"}
        assert called_metrics == ("distinct_open_vulnerabilities",)

    def test_unavailable_batch_matches_nothing_and_warns(self) -> None:
        capability = RecordingCapability(available=False, note="assurance store locked")
        result = _run(self.QUERY, capability)
        assert [item.id for item in result.entities] == []
        assert any("signals unavailable" in w and "locked" in w for w in result.warnings)


class TestPresentationOnlySignalAttributes:
    PRESENTATION = PresentationSpec(representation="exploration")
    QUERY = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(children=(
            AttributeCondition(attribute="type", comparator="eq",
                               value=ValueRef(literal="application-component")),
        )),
        derived=(SIGNAL_ATTR,),
    )

    def test_fetched_for_retained_population_only_in_one_call(self) -> None:
        capability = RecordingCapability({
            ("APP@1.aa.one", "distinct_open_vulnerabilities"): 5,
            ("APP@2.bb.two", "distinct_open_vulnerabilities"): 1,
        })
        projection = project_viewpoint_repository(
            "vp", None,
            catalog=_catalog(self.QUERY, self.PRESENTATION),
            read_access=_store(),
            registries=REGISTRIES,
            signal_capability=capability,  # type: ignore[arg-type]
        )
        assert len(capability.calls) == 1
        called_ids, _metrics = capability.calls[0]
        # Only the two retained application components — never the goal.
        assert set(called_ids) == {"APP@1.aa.one", "APP@2.bb.two"}
        assert not any("signals unavailable" in w for w in projection.warnings)

    def test_unavailable_presentation_batch_warns_and_styles_default(self) -> None:
        capability = RecordingCapability(available=False, note="snapshot changed")
        projection = project_viewpoint_repository(
            "vp", None,
            catalog=_catalog(self.QUERY, self.PRESENTATION),
            read_access=_store(),
            registries=REGISTRIES,
            signal_capability=capability,  # type: ignore[arg-type]
        )
        assert any("signals unavailable" in w for w in projection.warnings)
        # Entities still project — just without signal-driven styling.
        entity_items = [i for i in projection.items if i.item_kind == "entity"]
        assert len(entity_items) == 2


class TestNullCapability:
    def test_null_capability_warns_with_the_configuration_note(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(
                AttributeCondition(attribute="derived.open_vulns", comparator="gt",
                                   value=ValueRef(literal=0)),
            )),
            derived=(SIGNAL_ATTR,),
        )
        result = _run(query, NullSignalAttributeCapability())
        assert [item.id for item in result.entities] == []
        assert any("not configured" in w for w in result.warnings)

    def test_query_without_signal_attributes_never_calls_the_capability(self) -> None:
        capability = RecordingCapability()
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        _run(query, capability)
        assert capability.calls == []
