"""WU-1.3 acceptance: DatatypeVerificationProjection compiler.

Acceptance criteria:
- classifiers_by_id populated from candidate entities
- classifier_ids_by_name groups by normalized name
- usages_by_id populated from {kind:classifier} attribute type refs
- empty candidate → empty projection
- scope derived from scope_for_path on the entity path
- primitive type refs are NOT added to usages_by_id
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.diagram_types.datatype._projection import (
    AttributeTypeUsage,
    ClassifierDefinition,
    compile_projection,
)
from src.domain.diagrams.diagram_verification import BaseDiagramVerificationContext
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _entity(
    artifact_id: str,
    name: str = "Entity",
    host_diagram_id: str = "DT-A",
    status: str = "active",
    kind: str = "class",
    path: Path = Path("/fake/engagement"),
) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="classifier",
        name=name,
        version="0.1.0",
        status=status,
        domain="datatype",
        subdomain="classifier",
        path=path,
        keywords=(),
        extra={"classifier_kind": kind},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=artifact_id,
        host_diagram_id=host_diagram_id,
    )


def _diagram(
    artifact_id: str,
    diagram_entities: dict | None = None,
    diagram_type: str = "datatype",
    scope_path: Path = Path("/fake/engagement"),
) -> DiagramRecord:
    extra: dict = {}
    if diagram_entities is not None:
        extra["diagram-entities"] = diagram_entities
    return DiagramRecord(
        artifact_id=artifact_id,
        artifact_type="diagram",
        name=artifact_id,
        diagram_type=diagram_type,
        version="0.1.0",
        status="active",
        path=scope_path,
        extra=extra,
    )


class _StubRepo:
    def __init__(
        self,
        entities: list[EntityRecord] | None = None,
        diagrams: list[DiagramRecord] | None = None,
        scope: Literal["engagement", "enterprise", "unknown"] = "engagement",
    ) -> None:
        self._entities = {e.artifact_id: e for e in (entities or [])}
        self._diagrams = {d.artifact_id: d for d in (diagrams or [])}
        self._scope = scope

    def get_entity(self, aid: str) -> EntityRecord | None:
        return self._entities.get(aid)

    def get_diagram(self, aid: str) -> DiagramRecord | None:
        return self._diagrams.get(aid)

    def list_entities(self, *, artifact_type=None, domain=None, status=None) -> list[EntityRecord]:
        return [
            e for e in self._entities.values()
            if (artifact_type is None or e.artifact_type == artifact_type)
            and (domain is None or e.domain == domain)
            and (status is None or e.status == status)
        ]

    def list_diagrams(self, *, diagram_type=None, status=None) -> list[DiagramRecord]:
        return [
            d for d in self._diagrams.values()
            if (diagram_type is None or d.diagram_type == diagram_type)
            and (status is None or d.status == status)
        ]

    def scope_for_path(self, path: Path) -> Literal["engagement", "enterprise", "unknown"]:
        return self._scope


def _ctx() -> BaseDiagramVerificationContext:
    return BaseDiagramVerificationContext(
        fm={},
        loc="test.puml",
        scope="engagement",
        diagram_id="DT-test",
        allowed_connections=frozenset(),
        allowed_entities=frozenset(),
        catalogs=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_classifiers_by_id_populated() -> None:
    """compile_projection returns the classifier in classifiers_by_id."""
    repo = _StubRepo(entities=[_entity("CLF@1.ab.order", name="Order", kind="class")])
    proj = compile_projection(repo, _ctx())
    assert "CLF@1.ab.order" in proj.classifiers_by_id
    clf = proj.classifiers_by_id["CLF@1.ab.order"]
    assert isinstance(clf, ClassifierDefinition)
    assert clf.label == "Order"
    assert clf.kind == "class"
    assert clf.host_diagram_id == "DT-A"


def test_no_classifiers_empty_projection() -> None:
    """Empty candidate → all projection collections empty."""
    repo = _StubRepo()
    proj = compile_projection(repo, _ctx())
    assert proj.classifiers_by_id == {}
    assert proj.classifier_ids_by_name == {}
    assert proj.usages_by_id == {}


def test_classifier_ids_by_name_groups_by_name() -> None:
    """Two classifiers with the same name both appear in the name group."""
    eng_clf = _entity("CLF@1.ab.order", name="Order", host_diagram_id="DT-A")
    ent_clf = _entity("CLF@2.cd.order", name="Order", host_diagram_id="DT-B")
    repo = _StubRepo(entities=[eng_clf, ent_clf])
    proj = compile_projection(repo, _ctx())
    group = proj.classifier_ids_by_name.get("order")
    assert group is not None
    assert set(group) == {"CLF@1.ab.order", "CLF@2.cd.order"}


def test_classifier_ids_by_name_case_insensitive() -> None:
    """Name grouping is case-insensitive (normalized to lowercase)."""
    repo = _StubRepo(entities=[_entity("CLF@1.ab.x", name="MyClass")])
    proj = compile_projection(repo, _ctx())
    assert "myclass" in proj.classifier_ids_by_name


def test_usages_by_id_populated() -> None:
    """A {kind:classifier,id:...} attribute type produces a usage entry."""
    diag = _diagram(
        "DT-A",
        diagram_entities={
            "classifier": [
                {
                    "id": "CLF@1.ab.x",
                    "attributes": [
                        {"name": "order_ref", "type": {"kind": "classifier", "id": "CLF@2.cd.order"}},
                    ],
                }
            ]
        },
    )
    repo = _StubRepo(diagrams=[diag])
    proj = compile_projection(repo, _ctx())
    usages = proj.usages_by_id.get("CLF@2.cd.order")
    assert usages is not None and len(usages) == 1
    usage = usages[0]
    assert isinstance(usage, AttributeTypeUsage)
    assert usage.diagram_id == "DT-A"
    assert usage.classifier_local_id == "CLF@1.ab.x"
    assert usage.attr_name == "order_ref"


def test_usages_only_for_classifier_kind() -> None:
    """Primitive type refs are NOT added to usages_by_id."""
    diag = _diagram(
        "DT-A",
        diagram_entities={
            "classifier": [
                {
                    "id": "CLF@1.ab.x",
                    "attributes": [
                        {"name": "label", "type": {"kind": "primitive", "name": "String"}},
                    ],
                }
            ]
        },
    )
    repo = _StubRepo(diagrams=[diag])
    proj = compile_projection(repo, _ctx())
    assert proj.usages_by_id == {}


def test_classifier_scope_from_host_diagram() -> None:
    """Scope is derived from scope_for_path on the entity's path."""
    enterprise_path = Path("/fake/enterprise")
    ent_entity = _entity("CLF@2.cd.y", name="EnterpriseClass", path=enterprise_path)
    repo = _StubRepo(
        entities=[ent_entity],
        scope="enterprise",
    )
    proj = compile_projection(repo, _ctx())
    clf = proj.classifiers_by_id["CLF@2.cd.y"]
    assert clf.scope == "enterprise"


def test_non_datatype_diagrams_excluded_from_usages() -> None:
    """Diagrams with diagram_type != 'datatype' are not scanned for usages."""
    archimate_diag = _diagram(
        "ARC@1.xy.view",
        diagram_entities={
            "classifier": [
                {
                    "id": "CLF@1.ab.x",
                    "attributes": [
                        {"name": "ref", "type": {"kind": "classifier", "id": "CLF@2.cd.order"}},
                    ],
                }
            ]
        },
        diagram_type="archimate",
    )
    repo = _StubRepo(diagrams=[archimate_diag])
    proj = compile_projection(repo, _ctx())
    assert proj.usages_by_id == {}
