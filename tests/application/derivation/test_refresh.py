"""Tests for derivation refresh: compute_revision, compute_derivation_diff, apply_selection_delta.

Coverage:
  - compute_revision: stable hash; different content → different hash
  - compute_derivation_diff:
      - new candidates → new_entity_ids (not in selection yet)
      - already included → not in new_entity_ids
      - excluded → not in new_entity_ids (selection monotonicity)
      - gone → gone_entity_ids + remove_binding_ids
      - idempotence: fully-accepted diagram → empty diff
      - manual bindings (no derived_from) not proposed for removal
  - apply_selection_delta:
      - add_included merges into selection
      - remove_included removes from selection
      - excluded_entity_ids preserved across round-trips
      - unmatched derivation_id passthrough
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.application.derivation.explicit_selection import SPEC as ES_SPEC
from src.application.derivation.explicit_selection import derive as es_derive
from src.application.derivation.refresh import (
    SelectionDelta,
    apply_selection_delta,
    compute_derivation_diff,
    compute_revision,
)
from src.application.derivation.strategy_registry import DerivationStrategyCatalog, DerivationStrategyCatalogBuilder
from src.domain.viewpoints.view_derivations import DerivationSelection, SourceModelSnapshot, ViewDerivation
from tests.application.derivation._fixtures import FakeQuery, _entity


def _es_catalog() -> DerivationStrategyCatalog:
    b = DerivationStrategyCatalogBuilder()
    b.register(ES_SPEC, es_derive)
    return b.build()


_ES_CATALOG = _es_catalog()

_SNAPSHOT = SourceModelSnapshot(repo_scope="both")


def _make_vd(
    vd_id: str = "d1",
    entity_ids: list[str] | None = None,
    *,
    selection: DerivationSelection | None = None,
) -> ViewDerivation:
    params: dict[str, object] = {}
    if entity_ids is not None:
        params["entity_ids"] = entity_ids
    return ViewDerivation(
        id=vd_id,
        strategy="explicit-selection",
        strategy_version=1,
        source_model_snapshot=_SNAPSHOT,
        parameters=params,
        selection=selection,
    )


def _tmp_file(content: str = "hello") -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".puml")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


class TestComputeRevision:
    def test_stable_for_same_content(self) -> None:
        p = _tmp_file("abc")
        try:
            r1 = compute_revision(p)
            r2 = compute_revision(p)
            assert r1 == r2
        finally:
            p.unlink()

    def test_different_content_different_hash(self) -> None:
        p1, p2 = _tmp_file("aaa"), _tmp_file("bbb")
        try:
            assert compute_revision(p1) != compute_revision(p2)
        finally:
            p1.unlink()
            p2.unlink()

    def test_returns_16_hex_chars(self) -> None:
        p = _tmp_file("x")
        try:
            r = compute_revision(p)
            assert len(r) == 16
            assert all(c in "0123456789abcdef" for c in r)
        finally:
            p.unlink()


class TestComputeDerivationDiff:
    def _query_abc(self) -> FakeQuery:
        return FakeQuery(entities=[_entity("A@1"), _entity("B@2"), _entity("C@3")])

    def test_new_candidates_in_new_entity_ids(self) -> None:
        vd = _make_vd(entity_ids=["A@1", "B@2"])
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert "A@1" in diff.new_entity_ids
            assert "B@2" in diff.new_entity_ids
            assert diff.gone_entity_ids == []
        finally:
            p.unlink()

    def test_already_included_not_in_new(self) -> None:
        sel = DerivationSelection(included_entity_ids=("A@1",))
        vd = _make_vd(entity_ids=["A@1", "B@2"], selection=sel)
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert "A@1" not in diff.new_entity_ids
            assert "B@2" in diff.new_entity_ids
        finally:
            p.unlink()

    def test_selection_monotonicity_excluded_not_proposed(self) -> None:
        """Excluded entities must not reappear as new candidates (F4 property)."""
        sel = DerivationSelection(excluded_entity_ids=("B@2",))
        vd = _make_vd(entity_ids=["A@1", "B@2"], selection=sel)
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert "B@2" not in diff.new_entity_ids
            assert "A@1" in diff.new_entity_ids
        finally:
            p.unlink()

    def test_idempotence_fully_accepted_is_empty(self) -> None:
        """Refresh on a diagram where all candidates are already included → empty diff (F4)."""
        sel = DerivationSelection(included_entity_ids=("A@1", "B@2"))
        vd = _make_vd(entity_ids=["A@1", "B@2"], selection=sel)
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert diff.is_empty
            assert diff.new_entity_ids == []
            assert diff.gone_entity_ids == []
        finally:
            p.unlink()

    def test_gone_entity_in_gone_entity_ids(self) -> None:
        """Entity in included_entity_ids but not in current candidates is gone."""
        sel = DerivationSelection(included_entity_ids=("A@1", "GONE@99"))
        vd = _make_vd(entity_ids=["A@1"], selection=sel)
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert "GONE@99" in diff.gone_entity_ids
        finally:
            p.unlink()

    def test_manual_bindings_not_proposed_for_removal(self) -> None:
        """Bindings without derived_from are manual and must not appear in remove_binding_ids."""
        sel = DerivationSelection(included_entity_ids=("GONE@99",))
        vd = _make_vd(entity_ids=[], selection=sel)
        fm: dict[str, object] = {
            "bindings": [
                {
                    "id": "manual-bind",
                    "subject": {"kind": "entity", "id": "box1"},
                    "correspondence_kind": "represents",
                    "target": {"entity_id": "GONE@99"},
                    # NO derived_from → manual binding
                },
                {
                    "id": "derived-bind",
                    "subject": {"kind": "entity", "id": "box2"},
                    "correspondence_kind": "represents",
                    "target": {"entity_id": "GONE@99"},
                    "derived_from": "d1",  # matches vd.id
                },
            ]
        }
        p = _tmp_file("diag")
        try:
            diff = compute_derivation_diff(p, fm, vd, self._query_abc(), _ES_CATALOG)
            assert "manual-bind" not in diff.remove_binding_ids
            assert "derived-bind" in diff.remove_binding_ids
        finally:
            p.unlink()

    def test_raises_for_unregistered_strategy(self) -> None:
        vd = ViewDerivation(
            id="d1",
            strategy="no-such-strategy",
            strategy_version=1,
            source_model_snapshot=_SNAPSHOT,
        )
        p = _tmp_file("diag")
        try:
            with pytest.raises(ValueError, match="no-such-strategy"):
                compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
        finally:
            p.unlink()

    def test_base_revision_in_diff(self) -> None:
        vd = _make_vd(entity_ids=[])
        p = _tmp_file("content123")
        try:
            diff = compute_derivation_diff(p, {}, vd, self._query_abc(), _ES_CATALOG)
            assert diff.base_revision == compute_revision(p)
        finally:
            p.unlink()


class TestApplySelectionDelta:
    def _raw_vd(self, vd_id: str = "d1", **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": vd_id,
            "strategy": "explicit-selection",
            "strategy_version": 1,
            "source_model_snapshot": {"repo_scope": "both"},
        }
        base.update(overrides)
        return base

    def test_add_included_entity_ids(self) -> None:
        delta = SelectionDelta(add_included_entity_ids=["A@1", "B@2"])
        result = apply_selection_delta([self._raw_vd()], "d1", delta)
        sel = result[0].get("selection")
        assert isinstance(sel, dict)
        assert "A@1" in sel["included_entity_ids"]
        assert "B@2" in sel["included_entity_ids"]

    def test_remove_included_entity_ids(self) -> None:
        raw = self._raw_vd(selection={"included_entity_ids": ["A@1", "B@2"]})
        delta = SelectionDelta(remove_included_entity_ids=["A@1"])
        result = apply_selection_delta([raw], "d1", delta)
        sel = result[0].get("selection")
        assert isinstance(sel, dict)
        assert "A@1" not in sel.get("included_entity_ids", [])
        assert "B@2" in sel["included_entity_ids"]

    def test_add_excluded_preserved_after_round_trip(self) -> None:
        delta = SelectionDelta(add_excluded_entity_ids=["C@3"])
        result = apply_selection_delta([self._raw_vd()], "d1", delta)
        sel = result[0].get("selection")
        assert isinstance(sel, dict)
        assert "C@3" in sel["excluded_entity_ids"]

        # Apply an add_included on the same vd — excluded should still be there
        raw2 = result[0]
        delta2 = SelectionDelta(add_included_entity_ids=["A@1"])
        result2 = apply_selection_delta([raw2], "d1", delta2)
        sel2 = result2[0].get("selection")
        assert isinstance(sel2, dict)
        assert "C@3" in sel2.get("excluded_entity_ids", [])

    def test_unmatched_derivation_id_passthrough(self) -> None:
        raw = self._raw_vd("other-id")
        delta = SelectionDelta(add_included_entity_ids=["A@1"])
        result = apply_selection_delta([raw], "d1", delta)
        assert result[0] == raw  # unchanged

    def test_empty_delta_no_selection_added(self) -> None:
        raw = self._raw_vd()
        delta = SelectionDelta()
        result = apply_selection_delta([raw], "d1", delta)
        assert "selection" not in result[0]

    def test_empty_after_all_removed(self) -> None:
        raw = self._raw_vd(selection={"included_entity_ids": ["A@1"]})
        delta = SelectionDelta(remove_included_entity_ids=["A@1"])
        result = apply_selection_delta([raw], "d1", delta)
        # Selection with no contents should not appear
        sel = result[0].get("selection")
        assert sel is None or sel == {}
