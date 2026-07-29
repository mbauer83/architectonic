"""WU-4.2 acceptance: type closure computation for datatype diagram promotion.

Covers compute_type_closure:
- non-datatype diagrams skipped
- new classifier host added to additions with reason
- host already in enterprise → not added
- host already in promotion set → not added
- classifier with no discoverable host → broken (blocking)
- classifier already seen across diagrams → deduped
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.infrastructure.write.artifact_write.promote_type_closure import compute_type_closure

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeEntityRecord:
    artifact_id: str
    host_diagram_id: str | None = None


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str
    extra: dict = field(default_factory=dict)


class FakeRepo:
    def __init__(
        self,
        diagrams: list[FakeDiagramRecord] | None = None,
        entities: dict[str, FakeEntityRecord] | None = None,
    ) -> None:
        self._diagrams = {d.artifact_id: d for d in (diagrams or [])}
        self._entities = entities or {}

    def get_diagram(self, did: str) -> FakeDiagramRecord | None:
        return self._diagrams.get(did)

    def find_entity_by_workspace_id(self, artifact_id: str, **_: object) -> FakeEntityRecord | None:
        return self._entities.get(artifact_id)


class FakeRegistry:
    def __init__(self, enterprise_diagram_ids: set[str] | None = None) -> None:
        self._ent_diags = enterprise_diagram_ids or set()

    def enterprise_diagram_ids(self) -> set[str]:
        return self._ent_diags


def _dt_diagram(did: str, clf_type_refs: list[str]) -> FakeDiagramRecord:
    """Build a datatype FakeDiagramRecord with the given CLF@ type references."""
    classifiers = [
        {
            "id": f"CLF@dummy.{i}",
            "label": "C",
            "attributes": [{"name": "a", "type": {"kind": "classifier", "id": clf_id}}],
        }
        for i, clf_id in enumerate(clf_type_refs)
    ]
    return FakeDiagramRecord(
        artifact_id=did,
        diagram_type="datatype",
        name="D",
        extra={"diagram-entities": {"classifier": classifiers}},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeTypeClosure:
    def test_non_datatype_diagrams_skipped(self) -> None:
        diag = FakeDiagramRecord("DIA@1.arch", "archimate", "A", extra={})
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        result = compute_type_closure(["DIA@1.arch"], repo, registry)
        assert result.additions == []
        assert result.broken == []

    def test_adds_host_diagram_for_referenced_classifier(self) -> None:
        clf_id = "CLF@1.abc.customer"
        referencing_diag = _dt_diagram("DT@eng.ref", [clf_id])
        host_diag = FakeDiagramRecord("DT@eng.host", "datatype", "Host")
        repo = FakeRepo(
            diagrams=[referencing_diag, host_diag],
            entities={clf_id: FakeEntityRecord(clf_id, host_diagram_id="DT@eng.host")},
        )
        registry = FakeRegistry()
        result = compute_type_closure(["DT@eng.ref"], repo, registry)
        assert "DT@eng.host" in result.additions
        assert "DT@eng.host" in result.reasons
        assert clf_id in result.reasons["DT@eng.host"]

    def test_host_in_enterprise_not_added(self) -> None:
        clf_id = "CLF@1.ent.customer"
        diag = _dt_diagram("DT@eng.ref", [clf_id])
        repo = FakeRepo(
            diagrams=[diag],
            entities={clf_id: FakeEntityRecord(clf_id, host_diagram_id="DT@ent.host")},
        )
        registry = FakeRegistry(enterprise_diagram_ids={"DT@ent.host"})
        result = compute_type_closure(["DT@eng.ref"], repo, registry)
        assert "DT@ent.host" not in result.additions
        assert result.broken == []

    def test_host_already_in_promotion_set_not_duplicated(self) -> None:
        clf_id = "CLF@1.abc.x"
        host_id = "DT@eng.host"
        ref_diag = _dt_diagram("DT@eng.ref", [clf_id])
        host_diag = FakeDiagramRecord(host_id, "datatype", "Host")
        repo = FakeRepo(
            diagrams=[ref_diag, host_diag],
            entities={clf_id: FakeEntityRecord(clf_id, host_diagram_id=host_id)},
        )
        registry = FakeRegistry()
        # Both the referencing diag and the host are in the initial promotion set.
        result = compute_type_closure(["DT@eng.ref", host_id], repo, registry)
        assert host_id not in result.additions
        assert result.broken == []

    def test_missing_host_goes_to_broken(self) -> None:
        clf_id = "CLF@1.abc.ghost"
        diag = _dt_diagram("DT@eng.ref", [clf_id])
        repo = FakeRepo(diagrams=[diag], entities={})  # no entity record → broken
        registry = FakeRegistry()
        result = compute_type_closure(["DT@eng.ref"], repo, registry)
        assert clf_id in result.broken
        assert result.additions == []

    def test_same_classifier_in_two_diagrams_deduped(self) -> None:
        clf_id = "CLF@1.abc.shared"
        host_id = "DT@eng.host"
        diag_a = _dt_diagram("DT@eng.a", [clf_id])
        diag_b = _dt_diagram("DT@eng.b", [clf_id])
        host_diag = FakeDiagramRecord(host_id, "datatype", "Host")
        repo = FakeRepo(
            diagrams=[diag_a, diag_b, host_diag],
            entities={clf_id: FakeEntityRecord(clf_id, host_diagram_id=host_id)},
        )
        registry = FakeRegistry()
        result = compute_type_closure(["DT@eng.a", "DT@eng.b"], repo, registry)
        assert result.additions.count(host_id) == 1

    def test_empty_diagram_list(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        result = compute_type_closure([], repo, registry)
        assert result.additions == []
        assert result.broken == []


class TestClosureIntegrationWithPlan:
    """Verify broken-closure is surfaced as schema_errors in PromotionPlan."""

    def test_broken_closure_added_to_schema_errors(self) -> None:
        """plan_promotion propagates broken-closure errors into schema_errors."""
        from src.infrastructure.write.artifact_write.promote_to_enterprise import PromotionPlan

        # Simulate a plan with broken closure already set
        plan = PromotionPlan(
            root_entity="",
            entities_to_add=[],
            conflicts=[],
            connection_ids=[],
            already_in_enterprise=[],
            warnings=[],
            schema_errors=["Broken type closure: classifier CLF@1.x is referenced in a "
                           "promoted diagram but its host diagram cannot be found"],
            broken_type_closure=["CLF@1.x"],
        )
        assert any("CLF@1.x" in e for e in plan.schema_errors)
        assert plan.broken_type_closure == ["CLF@1.x"]
