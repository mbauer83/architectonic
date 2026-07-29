"""WU-4.1 acceptance: workspace classifiers indexed in promotion planning.

Covers:
- build_enterprise_classifier_indexes: empty, with CLF@ entities, with non-classifier entities
- plan_diagrams: same-id idempotent (no warning), name-clash advisory, non-datatype unaffected
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.infrastructure.write.artifact_write._promote_plan_content import plan_diagrams
from src.infrastructure.write.artifact_write._promote_planning import (
    ClassifierIndexes,
    build_enterprise_classifier_indexes,
)

# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeEntityRecord:
    artifact_id: str
    name: str
    artifact_type: str = "classifier"
    path: Path = field(default_factory=lambda: Path("/enterprise/dummy.md"))


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str
    extra: dict = field(default_factory=dict)


class FakeRepo:
    def __init__(
        self,
        entities: list[FakeEntityRecord] | None = None,
        diagrams: list[FakeDiagramRecord] | None = None,
    ) -> None:
        self._entities = {e.artifact_id: e for e in (entities or [])}
        self._diagrams = {d.artifact_id: d for d in (diagrams or [])}

    def get_entity(self, eid: str) -> FakeEntityRecord | None:
        return self._entities.get(eid)

    def list_diagrams(self) -> list[FakeDiagramRecord]:
        return list(self._diagrams.values())

    def get_diagram(self, did: str) -> FakeDiagramRecord | None:
        return self._diagrams.get(did)


class FakeRegistry:
    def __init__(
        self,
        enterprise_entity_ids: set[str] | None = None,
        enterprise_diagram_ids: set[str] | None = None,
    ) -> None:
        self._ent_entities = enterprise_entity_ids or set()
        self._ent_diagrams = enterprise_diagram_ids or set()

    def enterprise_entity_ids(self) -> set[str]:
        return self._ent_entities

    def enterprise_diagram_ids(self) -> set[str]:
        return self._ent_diagrams


# ---------------------------------------------------------------------------
# build_enterprise_classifier_indexes
# ---------------------------------------------------------------------------


class TestBuildEnterpriseClassifierIndexes:
    def test_empty_enterprise(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        indexes = build_enterprise_classifier_indexes(repo, registry)
        assert indexes.by_id == frozenset()
        assert indexes.by_name == {}

    def test_clf_entity_indexed_by_id_and_name(self) -> None:
        clf = FakeEntityRecord("CLF@1.abc.customer", "Customer")
        repo = FakeRepo(entities=[clf])
        registry = FakeRegistry(enterprise_entity_ids={"CLF@1.abc.customer"})
        indexes = build_enterprise_classifier_indexes(repo, registry)
        assert "CLF@1.abc.customer" in indexes.by_id
        assert indexes.by_name["customer"] == "CLF@1.abc.customer"

    def test_non_classifier_entity_excluded(self) -> None:
        ent = FakeEntityRecord("APP@1.abc.service", "My Service", artifact_type="application-component")
        repo = FakeRepo(entities=[ent])
        registry = FakeRegistry(enterprise_entity_ids={"APP@1.abc.service"})
        indexes = build_enterprise_classifier_indexes(repo, registry)
        assert indexes.by_id == frozenset()
        assert indexes.by_name == {}

    def test_name_normalisation(self) -> None:
        clf = FakeEntityRecord("CLF@1.abc.order", "  Order  ")
        repo = FakeRepo(entities=[clf])
        registry = FakeRegistry(enterprise_entity_ids={"CLF@1.abc.order"})
        indexes = build_enterprise_classifier_indexes(repo, registry)
        assert "order" in indexes.by_name

    def test_first_seen_wins_on_name_collision(self) -> None:
        """When two enterprise classifiers share a normalized name, first-seen wins."""
        clf_a = FakeEntityRecord("CLF@1.a.x", "Order")
        clf_b = FakeEntityRecord("CLF@1.b.x", "Order")
        repo = FakeRepo(entities=[clf_a, clf_b])
        registry = FakeRegistry(enterprise_entity_ids={"CLF@1.a.x", "CLF@1.b.x"})
        indexes = build_enterprise_classifier_indexes(repo, registry)
        assert indexes.by_name["order"] in {"CLF@1.a.x", "CLF@1.b.x"}


# ---------------------------------------------------------------------------
# plan_diagrams — classifier checks
# ---------------------------------------------------------------------------


def _datatype_diagram(did: str, classifiers: list[dict]) -> FakeDiagramRecord:
    return FakeDiagramRecord(
        artifact_id=did,
        diagram_type="datatype",
        name="Test Diagram",
        extra={"diagram-entities": {"classifier": classifiers}},
    )


class TestPlanDiagramsClassifiers:
    def test_same_id_in_enterprise_no_warning(self) -> None:
        """A classifier whose CLF@ id is already in enterprise → no warning (idempotent)."""
        clf_id = "CLF@1.abc.customer"
        diag = _datatype_diagram("DT@1.eng.d", [{"id": clf_id, "label": "Customer"}])
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        indexes = ClassifierIndexes(by_id=frozenset({clf_id}), by_name={"customer": clf_id})
        warnings: list[str] = []
        plan_diagrams(["DT@1.eng.d"], repo, registry, [], warnings, classifier_indexes=indexes)
        assert warnings == []

    def test_name_clash_different_id_emits_advisory(self) -> None:
        """Different CLF@ id but same name → advisory warning (non-blocking)."""
        eng_clf_id = "CLF@2.eng.customer"
        ent_clf_id = "CLF@1.ent.customer"
        diag = _datatype_diagram("DT@1.eng.d", [{"id": eng_clf_id, "label": "Customer"}])
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        indexes = ClassifierIndexes(by_id=frozenset({ent_clf_id}), by_name={"customer": ent_clf_id})
        warnings: list[str] = []
        plan_diagrams(["DT@1.eng.d"], repo, registry, [], warnings, classifier_indexes=indexes)
        assert any("Customer" in w and ent_clf_id in w for w in warnings)
        assert any("Advisory" in w or "advisory" in w for w in warnings)

    def test_new_classifier_no_warning(self) -> None:
        """A classifier not in enterprise by id or name → no warning."""
        diag = _datatype_diagram("DT@1.eng.d", [{"id": "CLF@1.new.x", "label": "Brand New"}])
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        indexes = ClassifierIndexes(by_id=frozenset(), by_name={})
        warnings: list[str] = []
        plan_diagrams(["DT@1.eng.d"], repo, registry, [], warnings, classifier_indexes=indexes)
        assert warnings == []

    def test_non_datatype_diagram_skipped(self) -> None:
        """Non-datatype diagrams are not inspected for classifier clashes."""
        diag = FakeDiagramRecord(
            "DIA@1.arch",
            "archimate",
            "Arch Diagram",
            extra={"diagram-entities": {"classifier": [{"id": "CLF@1.x.y", "label": "Clash"}]}},
        )
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        indexes = ClassifierIndexes(by_id=frozenset(), by_name={"clash": "CLF@9.ent.clash"})
        warnings: list[str] = []
        plan_diagrams(["DIA@1.arch"], repo, registry, [], warnings, classifier_indexes=indexes)
        assert warnings == []

    def test_no_indexes_skips_check(self) -> None:
        """When classifier_indexes is None, no classifier check is performed."""
        diag = _datatype_diagram("DT@1.d", [{"id": "CLF@1.x.y", "label": "Name"}])
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        warnings: list[str] = []
        plan_diagrams(["DT@1.d"], repo, registry, [], warnings)
        assert warnings == []
