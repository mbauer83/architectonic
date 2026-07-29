"""Unit coverage for the diagram-entity metadata patch: the whitelist (meta-only by
construction), id-addressing, and clear-vs-set merge. The full patch → edit_diagram → file path
is exercised end-to-end by the GUI Playwright smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.diagram_entity_metadata_patch import (
    _apply_meta_patch,
    _find_attribute,
    _find_classifier,
    _is_cleared,
)

# Whitelists in these unit tests are passed explicitly — the write op derives them from the
# diagram type's `editable_metadata` config (covered by test_editable_metadata_config.py), so the
# merge/refuse logic is tested independently of its source.
_CLASSIFIER_META_FIELDS = frozenset({"role", "provenance", "note", "tags"})
_ATTRIBUTE_META_FIELDS = frozenset({"multiplicity", "optional", "default", "role", "provenance", "note"})


class TestIsCleared:
    @pytest.mark.parametrize("value", [None, False, "", "   ", []])
    def test_cleared_values(self, value: object) -> None:
        assert _is_cleared(value) is True

    @pytest.mark.parametrize("value", ["x", "0", True, ["a"], "0..1"])
    def test_non_cleared_values(self, value: object) -> None:
        assert _is_cleared(value) is False


class TestApplyMetaPatch:
    def test_sets_whitelisted_classifier_fields(self) -> None:
        record = {"id": "c1", "label": "Order", "role": "old"}
        _apply_meta_patch(record, {"role": "new", "note": "why", "tags": ["a", "b"]}, _CLASSIFIER_META_FIELDS)
        assert record == {"id": "c1", "label": "Order", "role": "new", "note": "why", "tags": ["a", "b"]}

    def test_refuses_non_whitelisted_key(self) -> None:
        with pytest.raises(ValueError, match="not editable"):
            _apply_meta_patch({"id": "c1"}, {"label": "renamed"}, _CLASSIFIER_META_FIELDS)

    def test_attribute_whitelist_allows_structuralish_meta(self) -> None:
        record = {"id": "a1", "name": "amount"}
        _apply_meta_patch(
            record,
            {"multiplicity": "0..1", "optional": True, "default": "0", "role": "r", "provenance": "p", "note": "n"},
            _ATTRIBUTE_META_FIELDS,
        )
        assert record["multiplicity"] == "0..1"
        assert record["optional"] is True
        assert record["default"] == "0"
        assert record["note"] == "n"

    def test_attribute_whitelist_refuses_name_and_type(self) -> None:
        with pytest.raises(ValueError, match="not editable"):
            _apply_meta_patch({"id": "a1"}, {"name": "renamed"}, _ATTRIBUTE_META_FIELDS)
        with pytest.raises(ValueError, match="not editable"):
            _apply_meta_patch({"id": "a1"}, {"type": {"kind": "primitive", "name": "string"}}, _ATTRIBUTE_META_FIELDS)

    def test_empty_string_clears_the_field(self) -> None:
        record = {"id": "c1", "role": "old", "note": "keep"}
        _apply_meta_patch(record, {"role": ""}, _CLASSIFIER_META_FIELDS)
        assert "role" not in record
        assert record["note"] == "keep"

    def test_optional_false_clears_rather_than_writes_the_default(self) -> None:
        record = {"id": "a1", "optional": True}
        _apply_meta_patch(record, {"optional": False}, _ATTRIBUTE_META_FIELDS)
        assert "optional" not in record

    def test_untouched_siblings_survive(self) -> None:
        record = {"id": "c1", "label": "Order", "classifier_kind": "class", "attributes": [{"id": "a1"}]}
        _apply_meta_patch(record, {"note": "n"}, _CLASSIFIER_META_FIELDS)
        assert record["label"] == "Order"
        assert record["classifier_kind"] == "class"
        assert record["attributes"] == [{"id": "a1"}]


class TestAddressing:
    def _entities(self) -> dict[str, object]:
        return {"classifier": [
            {"id": "c1", "attributes": [{"id": "a1", "name": "x"}, {"id": "a2", "name": "y"}]},
            {"id": "c2", "attributes": []},
        ]}

    def test_find_classifier_by_id(self) -> None:
        assert _find_classifier(self._entities(), "c2")["id"] == "c2"

    def test_find_classifier_missing_raises(self) -> None:
        with pytest.raises(ValueError, match="classifier 'nope' not found"):
            _find_classifier(self._entities(), "nope")

    def test_find_attribute_by_id_not_position(self) -> None:
        classifier = self._entities()["classifier"][0]  # type: ignore[index]
        assert _find_attribute(classifier, "a2")["name"] == "y"

    def test_find_attribute_missing_raises(self) -> None:
        classifier = self._entities()["classifier"][0]  # type: ignore[index]
        with pytest.raises(ValueError, match="attribute 'nope' not found"):
            _find_attribute(classifier, "nope")


def test_endpoint_wires_the_write_op() -> None:
    """The GUI router delegates to the write op (guard against a silent unwiring)."""
    src = (Path(__file__).parents[3] / "src/infrastructure/gui/routers/_diagram_write.py").read_text()
    assert "patch_diagram_entity_metadata" in src
    assert "/api/diagram/entity-metadata" in src
