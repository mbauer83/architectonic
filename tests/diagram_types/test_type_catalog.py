"""WU-2.3: DatatypeTypeCatalog — query_datatype_types and query_type_usages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.diagram_types.datatype._type_catalog import (
    TypeCatalogResult,
    query_datatype_types,
    query_type_usages,
)

_PRIMITIVES = ["String", "Integer", "Number", "Boolean", "Date", "DateTime", "UUID"]

_CLF_A = "CLF@1.aa.order"
_CLF_B = "CLF@1.bb.customer"
_CLF_ENT = "CLF@1.cc.product"


@dataclass
class _MockVersion:
    generation: int = 42


@dataclass
class _MockEntity:
    artifact_id: str
    name: str
    path: Path = Path("/fake/eng/order.md")
    host_diagram_id: str = "DT-001"
    artifact_type: str = "classifier"


@dataclass
class _MockDiagram:
    artifact_id: str
    path: Path


@dataclass
class _FakeStore:
    _entities: list[_MockEntity] = field(default_factory=list)
    _scope_map: dict[Path, str] = field(default_factory=dict)
    _refs: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    _generation: int = 42
    _diagrams: dict[str, _MockDiagram] = field(default_factory=dict)

    def read_model_version(self) -> _MockVersion:
        return _MockVersion(generation=self._generation)

    def list_entities(self, *, artifact_type: str | None = None) -> list[_MockEntity]:
        if artifact_type is None:
            return list(self._entities)
        return [e for e in self._entities if e.artifact_type == artifact_type]

    def scope_for_path(self, path: Path) -> str:
        return self._scope_map.get(path, "engagement")

    def get_diagram(self, artifact_id: str) -> _MockDiagram | None:
        return self._diagrams.get(artifact_id)

    def diagrams_referencing_type_id(self, type_id: str) -> list[tuple[str, str, str]]:
        return list(self._refs.get(type_id, []))


def _store_with(
    entities: list[_MockEntity],
    scope_map: dict[Path, str] | None = None,
    refs: dict[str, list[tuple[str, str, str]]] | None = None,
    generation: int = 42,
    diagrams: dict[str, _MockDiagram] | None = None,
) -> _FakeStore:
    return _FakeStore(
        _entities=entities,
        _scope_map=scope_map or {},
        _refs=refs or {},
        _generation=generation,
        _diagrams=diagrams or {},
    )


# ── basic behavior ─────────────────────────────────────────────────────────────


def test_primitives_always_returned():
    store = _store_with([])
    result = query_datatype_types(store, _PRIMITIVES)
    assert result.primitives == _PRIMITIVES


def test_classifiers_returned():
    e = _MockEntity(_CLF_A, "Order")
    store = _store_with([e])
    result = query_datatype_types(store, _PRIMITIVES)
    assert len(result.classifiers) == 1
    clf = result.classifiers[0]
    assert clf.type_id == _CLF_A
    assert clf.label == "Order"
    assert clf.kind == "classifier"


def test_generation_propagated():
    store = _store_with([], generation=99)
    result = query_datatype_types(store, _PRIMITIVES)
    assert result.generation == 99


def test_empty_catalog():
    store = _store_with([])
    result = query_datatype_types(store, _PRIMITIVES)
    assert result.classifiers == []
    assert result.next_cursor is None


# ── filtering ─────────────────────────────────────────────────────────────────


def test_query_filter_substring():
    entities = [_MockEntity(_CLF_A, "Order"), _MockEntity(_CLF_B, "Customer")]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, query="ord")
    assert len(result.classifiers) == 1
    assert result.classifiers[0].type_id == _CLF_A


def test_query_filter_case_insensitive():
    entities = [_MockEntity(_CLF_A, "OrderLine")]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, query="ORDERLINE")
    assert len(result.classifiers) == 1


def test_scope_filter_engagement():
    eng_path = Path("/eng/order.md")
    ent_path = Path("/ent/product.md")
    entities = [
        _MockEntity(_CLF_A, "Order", path=eng_path),
        _MockEntity(_CLF_ENT, "Product", path=ent_path),
    ]
    store = _store_with(entities, scope_map={eng_path: "engagement", ent_path: "enterprise"})
    result = query_datatype_types(store, _PRIMITIVES, scope="engagement")
    assert len(result.classifiers) == 1
    assert result.classifiers[0].type_id == _CLF_A


def test_scope_filter_enterprise():
    eng_path = Path("/eng/order.md")
    ent_path = Path("/ent/product.md")
    entities = [
        _MockEntity(_CLF_A, "Order", path=eng_path),
        _MockEntity(_CLF_ENT, "Product", path=ent_path),
    ]
    store = _store_with(entities, scope_map={eng_path: "engagement", ent_path: "enterprise"})
    result = query_datatype_types(store, _PRIMITIVES, scope="enterprise")
    assert len(result.classifiers) == 1
    assert result.classifiers[0].type_id == _CLF_ENT


def test_engagement_diagram_sees_engagement_and_enterprise_classifiers():
    eng_path = Path("/eng/order.md")
    ent_path = Path("/ent/product.md")
    diagram_path = Path("/eng/diagram.md")
    e1 = _MockEntity(_CLF_A, "Order", path=eng_path, host_diagram_id="DT-001")
    e2 = _MockEntity(_CLF_ENT, "Product", path=ent_path, host_diagram_id="DT-002")
    store = _store_with(
        [e1, e2],
        scope_map={eng_path: "engagement", ent_path: "enterprise", diagram_path: "engagement"},
        diagrams={"DT-001": _MockDiagram("DT-001", diagram_path)},
    )
    result = query_datatype_types(store, _PRIMITIVES, diagram_id="DT-001")
    assert {classifier.type_id for classifier in result.classifiers} == {_CLF_A, _CLF_ENT}


def test_enterprise_diagram_excludes_engagement_classifiers():
    eng_path = Path("/eng/order.md")
    ent_path = Path("/ent/product.md")
    diagram_path = Path("/ent/diagram.md")
    entities = [
        _MockEntity(_CLF_A, "Order", path=eng_path),
        _MockEntity(_CLF_ENT, "Product", path=ent_path),
    ]
    store = _store_with(
        entities,
        scope_map={eng_path: "engagement", ent_path: "enterprise", diagram_path: "enterprise"},
        diagrams={"DT-ENT": _MockDiagram("DT-ENT", diagram_path)},
    )
    result = query_datatype_types(store, _PRIMITIVES, diagram_id="DT-ENT")
    assert [classifier.type_id for classifier in result.classifiers] == [_CLF_ENT]


def test_kind_filter_classifier_passes():
    store = _store_with([_MockEntity(_CLF_A, "Order")])
    result = query_datatype_types(store, _PRIMITIVES, kind="classifier")
    assert len(result.classifiers) == 1


def test_kind_filter_unknown_excludes_all():
    store = _store_with([_MockEntity(_CLF_A, "Order")])
    result = query_datatype_types(store, _PRIMITIVES, kind="enumeration")
    assert result.classifiers == []


# ── sort order ────────────────────────────────────────────────────────────────


def test_sort_enterprise_before_engagement():
    eng_path = Path("/eng/order.md")
    ent_path = Path("/ent/product.md")
    entities = [
        _MockEntity(_CLF_A, "Order", path=eng_path),
        _MockEntity(_CLF_ENT, "Product", path=ent_path),
    ]
    store = _store_with(entities, scope_map={eng_path: "engagement", ent_path: "enterprise"})
    result = query_datatype_types(store, _PRIMITIVES)
    assert result.classifiers[0].scope == "enterprise"
    assert result.classifiers[1].scope == "engagement"


def test_sort_alphabetical_within_scope():
    entities = [
        _MockEntity(_CLF_B, "Customer"),
        _MockEntity(_CLF_A, "Alpha"),
    ]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES)
    labels = [c.label for c in result.classifiers]
    assert labels == sorted(labels, key=str.lower)


# ── pagination ────────────────────────────────────────────────────────────────


def test_pagination_first_page():
    entities = [_MockEntity(f"CLF@1.{i:02d}.x", f"Type{i:02d}") for i in range(10)]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, limit=3)
    assert len(result.classifiers) == 3
    assert result.next_cursor == "3"


def test_pagination_second_page():
    entities = [_MockEntity(f"CLF@1.{i:02d}.x", f"Type{i:02d}") for i in range(10)]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, limit=3, cursor="3")
    assert len(result.classifiers) == 3
    assert result.next_cursor == "6"


def test_pagination_last_page_no_cursor():
    entities = [_MockEntity(f"CLF@1.{i:02d}.x", f"Type{i:02d}") for i in range(5)]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, limit=3, cursor="3")
    assert len(result.classifiers) == 2
    assert result.next_cursor is None


def test_pagination_exact_fit_no_cursor():
    entities = [_MockEntity(f"CLF@1.{i:02d}.x", f"Type{i:02d}") for i in range(3)]
    store = _store_with(entities)
    result = query_datatype_types(store, _PRIMITIVES, limit=3)
    assert result.next_cursor is None


# ── return type ────────────────────────────────────────────────────────────────


def test_result_is_type_catalog_result():
    store = _store_with([])
    result = query_datatype_types(store, _PRIMITIVES)
    assert isinstance(result, TypeCatalogResult)


# ── query_type_usages ─────────────────────────────────────────────────────────


def test_type_usages_returns_rows():
    refs = {_CLF_A: [("DT-001", "CLF@1.x.order", "customer")]}
    store = _store_with([], refs=refs)
    usages = query_type_usages(store, type_id=_CLF_A)
    assert len(usages) == 1
    assert usages[0]["diagram_id"] == "DT-001"
    assert usages[0]["classifier_local_id"] == "CLF@1.x.order"
    assert usages[0]["attr_name"] == "customer"


def test_type_usages_empty_for_unknown():
    store = _store_with([])
    usages = query_type_usages(store, type_id="CLF@0.xx.missing")
    assert usages == []


def test_type_usages_multiple_rows():
    refs = {_CLF_B: [("DT-001", "CLF@1.a.x", "ref1"), ("DT-002", "CLF@1.b.y", "ref2")]}
    store = _store_with([], refs=refs)
    usages = query_type_usages(store, type_id=_CLF_B)
    diagram_ids = {u["diagram_id"] for u in usages}
    assert diagram_ids == {"DT-001", "DT-002"}
