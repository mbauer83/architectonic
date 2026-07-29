"""WU-1.5 acceptance: E332 + W333 contributions via shared projection.

Acceptance criteria:
- E332: unknown primitive → fires
- E332: missing classifier id → fires
- E332: out-of-scope (enterprise diagram → engagement classifier) → fires
- E332: status violation (baselined diagram → draft classifier) → fires
- E332: known primitive → no fire
- E332: classifier id found, in-scope, in-status → no fire
- W333: classifier whose name collides with a primitive → fires (advisory)
- W333: classifier whose name collides with another in-scope classifier → fires (advisory)
- W333: fires only for classifiers DEFINED in the verified diagram (not mere referencers)
- W333: no collision → no fire
- Projection compiled once per diagram run (single compilation path)
- E332 and W333 have separate contributions via diagnostic_codes
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.datatype._contributions import _ProjectionBasedContributions
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext
from src.domain.ontology_representation.artifact_types import EntityRecord

_PRIMITIVE_NAMES: frozenset[str] = frozenset(
    ["String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"]
)
_CONTRIB = _ProjectionBasedContributions(_PRIMITIVE_NAMES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(
    fm: dict,
    scope: str = "engagement",
    diagram_id: str = "DT-A",
) -> BaseDiagramVerificationContext:
    return BaseDiagramVerificationContext(
        fm=fm,
        loc="test.puml",
        scope=scope,  # type: ignore[arg-type]
        diagram_id=diagram_id,
        allowed_connections=frozenset(),
        allowed_entities=frozenset(),
        catalogs=None,
    )


def _entity(
    artifact_id: str,
    name: str = "Order",
    status: str = "active",
    scope_str: str = "engagement",
    path: Path | None = None,
    host_diagram_id: str = "DT-A",
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="classifier",
        name=name,
        version="0.1.0",
        status=status,
        domain="datatype",
        subdomain="classifier",
        path=path or Path(f"/fake/{scope_str}/order.md"),
        keywords=(),
        extra={"classifier_kind": "class"},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
        host_diagram_id=host_diagram_id,
    )


class _StubRepo:
    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        scope: Literal["engagement", "enterprise", "unknown"] = "engagement",
    ) -> None:
        self._entities = {e.artifact_id: e for e in (entities or [])}
        self._scope = scope

    def get_entity(self, aid: str) -> EntityRecord | None:
        return self._entities.get(aid)

    def get_diagram(self, aid: str) -> object:
        return None

    def list_entities(self, *, artifact_type=None, domain=None, status=None) -> list:
        return [
            e for e in self._entities.values()
            if (artifact_type is None or e.artifact_type == artifact_type)
        ]

    def list_diagrams(self, *, diagram_type=None, status=None) -> list:
        return []

    def scope_for_path(self, path: Path) -> str:
        return self._scope


def _fm_with_attrs(
    clf_id: str,
    attrs: list,
    status: str = "active",
) -> dict:
    return {
        "artifact-id": "DT-A",
        "diagram-type": "datatype",
        "status": status,
        "diagram-entities": {
            "classifier": [
                {"id": clf_id, "classifier_kind": "class", "attributes": attrs}
            ]
        },
    }


def _run(
    fm: dict,
    repo: _StubRepo | None = None,
    scope: str = "engagement",
    diagram_id: str = "DT-A",
) -> tuple[list, list]:
    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    _CONTRIB.run(repo or _StubRepo(), _ctx(fm, scope=scope, diagram_id=diagram_id), result)
    e332 = [i for i in result.issues if i.code == "E332"]
    w333 = [i for i in result.issues if i.code == "W333"]
    return e332, w333


# ---------------------------------------------------------------------------
# E332 tests
# ---------------------------------------------------------------------------


def test_e332_unknown_primitive() -> None:
    fm = _fm_with_attrs("CLF@1.ab.x", [{"name": "f", "type": {"kind": "primitive", "name": "Blob"}}])
    e332, _ = _run(fm)
    assert len(e332) == 1
    assert e332[0].severity == Severity.ERROR
    assert e332[0].details["reason"] == "unknown-primitive"


def test_e332_missing_classifier_id() -> None:
    fm = _fm_with_attrs(
        "CLF@1.ab.x",
        [{"name": "f", "type": {"kind": "classifier", "id": "CLF@9.zz.missing"}}],
    )
    e332, _ = _run(fm)
    assert len(e332) == 1
    assert e332[0].details["reason"] == "missing-id"


def test_e332_out_of_scope_enterprise_sees_engagement() -> None:
    eng_clf = _entity("CLF@1.ab.order", name="Order", scope_str="engagement")
    repo = _StubRepo([eng_clf], scope="engagement")
    fm = _fm_with_attrs(
        "CLF@2.cd.x",
        [{"name": "f", "type": {"kind": "classifier", "id": "CLF@1.ab.order"}}],
    )
    e332, _ = _run(fm, repo=repo, scope="enterprise")
    assert len(e332) == 1
    assert e332[0].details["reason"] == "out-of-scope"


def test_e332_status_violation_baselined_refs_draft() -> None:
    draft_clf = _entity("CLF@1.ab.order", name="Order", status="draft")
    repo = _StubRepo([draft_clf], scope="engagement")
    fm = _fm_with_attrs(
        "CLF@2.cd.x",
        [{"name": "f", "type": {"kind": "classifier", "id": "CLF@1.ab.order"}}],
        status="baselined",
    )
    e332, _ = _run(fm, repo=repo)
    assert len(e332) == 1
    assert e332[0].details["reason"] == "status-violation"


def test_e332_known_primitive_no_fire() -> None:
    fm = _fm_with_attrs(
        "CLF@1.ab.x", [{"name": "f", "type": {"kind": "primitive", "name": "String"}}]
    )
    e332, _ = _run(fm)
    assert e332 == []


def test_e332_known_classifier_no_fire() -> None:
    clf = _entity("CLF@1.ab.order", name="Order", status="active")
    repo = _StubRepo([clf], scope="engagement")
    fm = _fm_with_attrs(
        "CLF@2.cd.x",
        [{"name": "f", "type": {"kind": "classifier", "id": "CLF@1.ab.order"}}],
    )
    e332, _ = _run(fm, repo=repo)
    assert e332 == []


def test_e332_same_write_intra_diagram_reference_resolves() -> None:
    """A reference to a classifier defined in the SAME, not-yet-committed diagram resolves.

    The candidate (repo) is empty; resolution must come from the diagram under verification
    itself (compile_projection's same-write step).
    """
    fm = {
        "artifact-id": "DT-A",
        "diagram-type": "datatype",
        "status": "draft",
        "diagram-entities": {"classifier": [
            {
                "id": "CLF@1.ab.order", "classifier_kind": "class", "label": "Order",
                "attributes": [{"name": "color", "type": {"kind": "classifier", "id": "CLF@1.cd.color"}}],
            },
            {"id": "CLF@1.cd.color", "classifier_kind": "enumeration", "label": "Color"},
        ]},
    }
    e332, _ = _run(fm)  # empty candidate — only the same-write contract can resolve the ref
    assert e332 == []


def test_e332_details_fields_present() -> None:
    fm = _fm_with_attrs(
        "CLF@1.ab.x", [{"name": "my_field", "type": {"kind": "primitive", "name": "Blob"}}]
    )
    e332, _ = _run(fm)
    assert len(e332) == 1
    d = e332[0].details
    assert d is not None
    assert d["classifier"] == "CLF@1.ab.x"
    assert d["attr_name"] == "my_field"
    assert "type_ref" in d
    assert "reason" in d
    assert "candidates" in d


def test_e332_no_type_field_no_fire() -> None:
    """Attributes without a type field are skipped (schema check handles that separately)."""
    fm = _fm_with_attrs("CLF@1.ab.x", [{"name": "f"}])
    e332, _ = _run(fm)
    assert e332 == []


# ---------------------------------------------------------------------------
# W333 tests
# ---------------------------------------------------------------------------


def test_w333_primitive_name_collision() -> None:
    """A classifier whose label matches a built-in primitive triggers W333."""
    clf = _entity("CLF@1.ab.string", name="String")
    repo = _StubRepo([clf])
    fm = _fm_with_attrs("CLF@1.ab.string", [])
    _, w333 = _run(fm, repo=repo)
    assert len(w333) == 1
    assert w333[0].severity == Severity.WARNING
    assert "String" in w333[0].message


def test_w333_classifier_name_collision() -> None:
    """A classifier whose name matches another in-scope classifier triggers W333."""
    clf_a = _entity("CLF@1.ab.order", name="Order", scope_str="engagement")
    clf_b = _entity("CLF@2.cd.order", name="Order", scope_str="engagement")
    repo = _StubRepo([clf_a, clf_b])
    # Diagram defines CLF@1 but CLF@2 also exists with same name
    fm = _fm_with_attrs("CLF@1.ab.order", [])
    _, w333 = _run(fm, repo=repo)
    assert len(w333) == 1
    assert "CLF@2.cd.order" in w333[0].message


def test_w333_no_collision_no_fire() -> None:
    clf = _entity("CLF@1.ab.order", name="Order")
    repo = _StubRepo([clf])
    fm = _fm_with_attrs("CLF@1.ab.order", [])
    _, w333 = _run(fm, repo=repo)
    assert w333 == []


def test_w333_fires_only_for_defining_diagram() -> None:
    """A classifier defined in diagram B should not trigger W333 when verifying diagram A."""
    # DT-A has CLF@1 referencing CLF@2 as a type (not defining it)
    # CLF@2 has a name collision — but since DT-A doesn't define CLF@2, no W333 for DT-A
    clf1 = _entity("CLF@1.ab.x", name="UniqueNameA", host_diagram_id="DT-A")
    clf2a = _entity("CLF@2.cd.y", name="SharedName", host_diagram_id="DT-B")
    clf2b = _entity("CLF@3.ef.z", name="SharedName", host_diagram_id="DT-C")
    repo = _StubRepo([clf1, clf2a, clf2b])
    # DT-A only defines CLF@1 (unique name), references CLF@2 as a type
    fm = {
        "artifact-id": "DT-A",
        "diagram-type": "datatype",
        "status": "active",
        "diagram-entities": {
            "classifier": [
                {
                    "id": "CLF@1.ab.x",
                    "classifier_kind": "class",
                    "attributes": [
                        {"name": "f", "type": {"kind": "classifier", "id": "CLF@2.cd.y"}},
                    ],
                }
            ]
        },
    }
    _, w333 = _run(fm, repo=repo, diagram_id="DT-A")
    assert w333 == []


def test_w333_enterprise_scope_excludes_engagement_from_collision_check() -> None:
    """In an enterprise diagram, engagement classifiers are out of scope for W333 collision."""
    clf_enterprise = _entity(
        "CLF@1.ab.order", name="Order", scope_str="enterprise", path=Path("/fake/enterprise/o.md")
    )
    clf_engagement = _entity(
        "CLF@2.cd.order", name="Order", scope_str="engagement", path=Path("/fake/engagement/o.md")
    )
    # Both have the same name, but engagement is out of scope for enterprise diagram

    class _MultiScopeRepo:
        def list_entities(self, *, artifact_type=None, domain=None, status=None):
            return [clf_enterprise, clf_engagement]

        def list_diagrams(self, *, diagram_type=None, status=None):
            return []

        def scope_for_path(self, path: Path) -> str:
            return "enterprise" if "enterprise" in str(path) else "engagement"

    result = VerificationResult(path=Path("test.puml"), file_type="diagram")
    fm = _fm_with_attrs("CLF@1.ab.order", [])
    fm["artifact-id"] = "DT-ENT"
    _CONTRIB.run(
        _MultiScopeRepo(),
        _ctx(fm, scope="enterprise", diagram_id="DT-ENT"),
        result,
    )
    w333 = [i for i in result.issues if i.code == "W333"]
    assert w333 == []


# ---------------------------------------------------------------------------
# diagnostic_codes registration
# ---------------------------------------------------------------------------


def test_diagnostic_codes_present() -> None:
    assert "E332" in _CONTRIB.diagnostic_codes
    assert "W333" in _CONTRIB.diagnostic_codes
