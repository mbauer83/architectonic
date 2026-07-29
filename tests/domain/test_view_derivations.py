"""Tests for ViewDerivation data model, schema, parsing, and verifier rules.

Coverage:
  - ViewDerivation parse/round-trip
  - Verifier rules: E409 (derived_from), E410 (dup id), E411 (unknown strategy),
    E412 (unsupported filter), E413 (invalid repo_scope)
  - Clean inputs produce no issues
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.derivation.strategy_registry import (
    DerivationStrategyCatalog,
    DerivationStrategyCatalogBuilder,
    StrategySpec,
)
from src.application.verification._verifier_rules_view_derivations import (
    check_bindings_derived_from,
    check_view_derivations,
    collect_view_derivation_ids,
)
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.viewpoints.view_derivations import (
    VIEW_DERIVATIONS_SCHEMA,
    DerivationSelection,
    PathProvenance,
    SourceModelSnapshot,
    ViewDerivation,
    parse_view_derivation,
    parse_view_derivations,
    view_derivation_to_dict,
)

_LOC = "/test/diagram.puml"


def _result() -> VerificationResult:
    return VerificationResult(path=Path(_LOC), file_type="diagram")


def _codes(r: VerificationResult) -> set[str]:
    return {i.code for i in r.issues if i.severity == "error"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class TestSourceModelSnapshot:
    def test_basic(self) -> None:
        snap = SourceModelSnapshot(repo_scope="both")
        assert snap.repo_scope == "both"
        assert snap.root_entity_id is None
        assert snap.root_entity_ids is None

    def test_with_root_entity_id(self) -> None:
        snap = SourceModelSnapshot(repo_scope="engagement", root_entity_id="APP@1.a.b")
        assert snap.root_entity_id == "APP@1.a.b"

    def test_with_root_entity_ids(self) -> None:
        snap = SourceModelSnapshot(repo_scope="both", root_entity_ids=("A@1.a.b", "B@2.c.d"))
        assert snap.root_entity_ids == ("A@1.a.b", "B@2.c.d")


class TestDerivationSelection:
    def test_defaults_are_empty_tuples(self) -> None:
        sel = DerivationSelection()
        assert sel.included_entity_ids == ()
        assert sel.excluded_entity_ids == ()

    def test_with_ids(self) -> None:
        sel = DerivationSelection(included_entity_ids=("A@1.a.b",), excluded_entity_ids=("B@2.c.d",))
        assert "A@1.a.b" in sel.included_entity_ids
        assert "B@2.c.d" in sel.excluded_entity_ids

    def test_default_path_provenance_is_empty(self) -> None:
        assert DerivationSelection().path_provenance == {}

    def test_with_path_provenance(self) -> None:
        provenance = PathProvenance(certainty="certain", connection_type="archimate-realization")
        sel = DerivationSelection(included_paths=("A@fwd|B@fwd",), path_provenance={"A@fwd|B@fwd": provenance})
        assert sel.path_provenance["A@fwd|B@fwd"].certainty == "certain"
        assert sel.path_provenance["A@fwd|B@fwd"].connection_type == "archimate-realization"


class TestViewDerivation:
    def _minimal_vd(self) -> ViewDerivation:
        return ViewDerivation(
            id="derive-1",
            strategy="explicit-selection",
            strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="both"),
        )

    def test_minimal_fields(self) -> None:
        vd = self._minimal_vd()
        assert vd.id == "derive-1"
        assert vd.strategy == "explicit-selection"
        assert vd.strategy_version == 1
        assert vd.parameters == {}
        assert vd.selection is None
        assert vd.generated_at is None

    def test_with_selection(self) -> None:
        vd = ViewDerivation(
            id="d",
            strategy="s",
            strategy_version=1,
            source_model_snapshot=SourceModelSnapshot(repo_scope="engagement"),
            selection=DerivationSelection(included_entity_ids=("X@1.a.b",)),
        )
        assert vd.selection is not None
        assert "X@1.a.b" in vd.selection.included_entity_ids


# ---------------------------------------------------------------------------
# Parsing and round-trip
# ---------------------------------------------------------------------------


class TestParseViewDerivation:
    def _raw(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": "derive-1",
            "strategy": "explicit-selection",
            "strategy_version": 1,
            "source_model_snapshot": {"repo_scope": "both"},
        }
        base.update(overrides)
        return base

    def test_minimal_parse(self) -> None:
        vd = parse_view_derivation(self._raw())
        assert vd.id == "derive-1"
        assert vd.strategy == "explicit-selection"
        assert vd.strategy_version == 1
        assert vd.source_model_snapshot.repo_scope == "both"

    def test_parse_with_parameters(self) -> None:
        raw = self._raw(parameters={"max_hops": 2, "pre_filters": {"direction": "outbound"}})
        vd = parse_view_derivation(raw)
        assert vd.parameters["max_hops"] == 2

    def test_parse_with_selection(self) -> None:
        raw = self._raw(selection={
            "included_entity_ids": ["APP@1.a.b"],
            "excluded_connection_ids": ["A@1---B@2@@serving"],
        })
        vd = parse_view_derivation(raw)
        assert vd.selection is not None
        assert "APP@1.a.b" in vd.selection.included_entity_ids
        assert "A@1---B@2@@serving" in vd.selection.excluded_connection_ids

    def test_parse_with_path_provenance(self) -> None:
        raw = self._raw(selection={
            "included_paths": ["A@fwd|B@fwd"],
            "path_provenance": {"A@fwd|B@fwd": {"certainty": "certain", "connection_type": "archimate-realization"}},
        })
        vd = parse_view_derivation(raw)
        assert vd.selection is not None
        entry = vd.selection.path_provenance["A@fwd|B@fwd"]
        assert entry.certainty == "certain"
        assert entry.connection_type == "archimate-realization"

    def test_parse_with_malformed_path_provenance_entry_skipped(self) -> None:
        raw = self._raw(selection={"path_provenance": {"A@fwd": {"certainty": "certain"}}})
        vd = parse_view_derivation(raw)
        assert vd.selection is not None
        assert vd.selection.path_provenance == {}

    def test_parse_with_generated_at(self) -> None:
        raw = self._raw(generated_at="2026-05-30")
        vd = parse_view_derivation(raw)
        assert vd.generated_at == "2026-05-30"

    def test_missing_snapshot_raises(self) -> None:
        raw = self._raw()
        raw.pop("source_model_snapshot")
        with pytest.raises(ValueError, match="source_model_snapshot"):
            parse_view_derivation(raw)

    def test_parse_view_derivations_empty(self) -> None:
        assert parse_view_derivations(None) == []
        assert parse_view_derivations([]) == []

    def test_parse_view_derivations_skips_non_dicts(self) -> None:
        result = parse_view_derivations([self._raw(), "bad", None])  # type: ignore[list-item]
        assert len(result) == 1

    def test_roundtrip(self) -> None:
        raw = self._raw(
            parameters={"diagram_type": "c4-container"},
            selection={"included_entity_ids": ["APP@1.a.b"]},
            generated_at="2026-05-30",
        )
        vd = parse_view_derivation(raw)
        d = view_derivation_to_dict(vd)
        vd2 = parse_view_derivation(d)
        assert vd == vd2

    def test_roundtrip_with_path_provenance(self) -> None:
        raw = self._raw(
            selection={
                "included_paths": ["A@fwd|B@fwd"],
                "path_provenance": {
                    "A@fwd|B@fwd": {"certainty": "certain", "connection_type": "archimate-realization"}
                },
            },
        )
        vd = parse_view_derivation(raw)
        vd2 = parse_view_derivation(view_derivation_to_dict(vd))
        assert vd == vd2


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


class TestViewDerivationsSchema:
    def test_is_array(self) -> None:
        assert VIEW_DERIVATIONS_SCHEMA["type"] == "array"

    def test_item_required_fields(self) -> None:
        req = VIEW_DERIVATIONS_SCHEMA["items"]["required"]  # type: ignore[index]
        assert "id" in req
        assert "strategy" in req
        assert "strategy_version" in req
        assert "source_model_snapshot" in req

    def test_repo_scope_enum(self) -> None:
        props = VIEW_DERIVATIONS_SCHEMA["items"]["properties"]["source_model_snapshot"]["properties"]  # type: ignore[index]
        enum = props["repo_scope"]["enum"]
        assert set(enum) == {"enterprise", "engagement", "both"}


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


class TestStrategyRegistry:
    def test_lookup_unknown_returns_none(self) -> None:
        catalog = DerivationStrategyCatalogBuilder().build()
        assert catalog.lookup_strategy("unknown", 1) is None

    def test_register_and_lookup(self) -> None:
        spec = StrategySpec(name="explicit-selection", version=1, supported_filters=frozenset({"direction"}))
        b = DerivationStrategyCatalogBuilder()
        b.register(spec)
        catalog = b.build()
        found = catalog.lookup_strategy("explicit-selection", 1)
        assert found is not None
        assert found.supported_filters == frozenset({"direction"})

    def test_different_versions_independent(self) -> None:
        v1 = StrategySpec(name="s", version=1, supported_filters=frozenset({"a"}))
        v2 = StrategySpec(name="s", version=2, supported_filters=frozenset({"a", "b"}))
        b = DerivationStrategyCatalogBuilder()
        b.register(v1)
        b.register(v2)
        catalog = b.build()
        assert catalog.lookup_strategy("s", 1) == v1
        assert catalog.lookup_strategy("s", 2) == v2


# ---------------------------------------------------------------------------
# Verifier rule helpers
# ---------------------------------------------------------------------------


def _vd_entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "derive-1",
        "strategy": "my-strategy",
        "strategy_version": 1,
        "source_model_snapshot": {"repo_scope": "both"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# E410: duplicate view_derivations.id
# ---------------------------------------------------------------------------


class TestE410DuplicateVdId:
    def test_duplicate_id_raises_e410(self) -> None:
        fm = {"view_derivations": [_vd_entry(id="d1"), _vd_entry(id="d1")]}
        r = _result()
        check_view_derivations(fm, r, _LOC)
        assert "E410" in _codes(r)

    def test_unique_ids_ok(self) -> None:
        fm = {"view_derivations": [_vd_entry(id="d1"), _vd_entry(id="d2")]}
        r = _result()
        check_view_derivations(fm, r, _LOC)
        assert "E410" not in _codes(r)

    def test_no_view_derivations_ok(self) -> None:
        r = _result()
        check_view_derivations({}, r, _LOC)
        assert not r.issues


# ---------------------------------------------------------------------------
# E413: invalid repo_scope
# ---------------------------------------------------------------------------


class TestE413InvalidRepoScope:
    def test_invalid_scope_raises_e413(self) -> None:
        entry = _vd_entry(source_model_snapshot={"repo_scope": "all"})
        fm = {"view_derivations": [entry]}
        r = _result()
        check_view_derivations(fm, r, _LOC)
        assert "E413" in _codes(r)

    def test_valid_scopes_ok(self) -> None:
        for scope in ("enterprise", "engagement", "both"):
            entry = _vd_entry(source_model_snapshot={"repo_scope": scope})
            fm = {"view_derivations": [entry]}
            r = _result()
            check_view_derivations(fm, r, _LOC)
            assert "E413" not in _codes(r), f"scope {scope!r} should be valid"


# ---------------------------------------------------------------------------
# E411: unknown strategy
# ---------------------------------------------------------------------------


class TestE411UnknownStrategy:
    def _empty_catalog(self) -> DerivationStrategyCatalog:
        return DerivationStrategyCatalogBuilder().build()

    def _catalog_with_my_strategy(self) -> DerivationStrategyCatalog:
        b = DerivationStrategyCatalogBuilder()
        b.register(StrategySpec(name="my-strategy", version=1, supported_filters=frozenset()))
        return b.build()

    def test_unknown_strategy_raises_e411(self) -> None:
        fm = {"view_derivations": [_vd_entry(strategy="no-such-strategy", strategy_version=1)]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._empty_catalog())
        assert "E411" in _codes(r)

    def test_registered_strategy_ok(self) -> None:
        fm = {"view_derivations": [_vd_entry()]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._catalog_with_my_strategy())
        assert "E411" not in _codes(r)

    def test_empty_strategy_string_skipped(self) -> None:
        fm = {"view_derivations": [_vd_entry(strategy="")]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._empty_catalog())
        assert "E411" not in _codes(r)


# ---------------------------------------------------------------------------
# E412: unsupported pre_filter
# ---------------------------------------------------------------------------


class TestE412UnsupportedFilter:
    def _catalog(self) -> DerivationStrategyCatalog:
        b = DerivationStrategyCatalogBuilder()
        b.register(StrategySpec(
            name="my-strategy", version=1,
            supported_filters=frozenset({"direction", "max_hops"}),
        ))
        return b.build()

    def test_unsupported_filter_raises_e412(self) -> None:
        entry = _vd_entry(parameters={"pre_filters": {"unknown_filter": True}})
        fm = {"view_derivations": [entry]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._catalog())
        assert "E412" in _codes(r)

    def test_supported_filter_ok(self) -> None:
        entry = _vd_entry(parameters={"pre_filters": {"direction": "outbound"}})
        fm = {"view_derivations": [entry]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._catalog())
        assert "E412" not in _codes(r)

    def test_no_pre_filters_ok(self) -> None:
        entry = _vd_entry(parameters={"diagram_type": "c4-container"})
        fm = {"view_derivations": [entry]}
        r = _result()
        check_view_derivations(fm, r, _LOC, catalog=self._catalog())
        assert "E412" not in _codes(r)


# ---------------------------------------------------------------------------
# E409: binding derived_from references unknown view_derivations.id
# ---------------------------------------------------------------------------


class TestE409DerivedFrom:
    def _binding(self, derived_from: str | None = None) -> dict[str, object]:
        b: dict[str, object] = {
            "id": "bind-1",
            "subject": {"kind": "entity", "id": "box1"},
            "correspondence_kind": "represents",
            "target": {"entity_id": "APP@1.a.b"},
        }
        if derived_from is not None:
            b["derived_from"] = derived_from
        return b

    def test_dangling_derived_from_raises_e409(self) -> None:
        fm = {"bindings": [self._binding(derived_from="no-such-vd")]}
        r = _result()
        check_bindings_derived_from(fm, set(), r, _LOC)
        assert "E409" in _codes(r)

    def test_known_derived_from_ok(self) -> None:
        fm = {"bindings": [self._binding(derived_from="derive-1")]}
        r = _result()
        check_bindings_derived_from(fm, {"derive-1"}, r, _LOC)
        assert "E409" not in _codes(r)

    def test_no_derived_from_ok(self) -> None:
        fm = {"bindings": [self._binding()]}
        r = _result()
        check_bindings_derived_from(fm, set(), r, _LOC)
        assert "E409" not in _codes(r)

    def test_empty_bindings_ok(self) -> None:
        r = _result()
        check_bindings_derived_from({}, set(), r, _LOC)
        assert not r.issues


# ---------------------------------------------------------------------------
# collect_view_derivation_ids
# ---------------------------------------------------------------------------


class TestCollectViewDerivationIds:
    def test_empty_fm(self) -> None:
        assert collect_view_derivation_ids({}) == set()

    def test_collects_ids(self) -> None:
        fm = {"view_derivations": [
            {"id": "derive-1", "strategy": "s", "strategy_version": 1,
             "source_model_snapshot": {"repo_scope": "both"}},
            {"id": "derive-2", "strategy": "s", "strategy_version": 1,
             "source_model_snapshot": {"repo_scope": "both"}},
        ]}
        ids = collect_view_derivation_ids(fm)
        assert ids == {"derive-1", "derive-2"}
