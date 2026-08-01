"""Properties-table values are a first-class attribute surface: the parser decodes
them into `EntityRecord.attributes`, attribute reads consult them before
frontmatter `extra`, and scale styling over a mixed entity+connection population
neither loses the values nor cries schema drift."""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.parsing import parse_entity
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value

_DOMAINS = frozenset({"strategy", "motivation", "business", "application", "technology", "common"})


def _write_entity(tmp_path: Path, *, attribute_types: str = "", properties_rows: str) -> Path:
    model_root = tmp_path / "model"
    path = model_root / "strategy" / "resource" / "RES@1.abc.example-asset.md"
    path.parent.mkdir(parents=True)
    frontmatter_types = f"attribute-types:\n{attribute_types}" if attribute_types else ""
    path.write_text(
        f"""---
artifact-id: RES@1.abc.example-asset
artifact-type: resource
name: Example Asset
version: 0.1.0
status: active
{frontmatter_types}
---

<!-- §content -->

## Example Asset

An asset used to verify the attribute surface.

## Properties

| Attribute | Value |
|---|---|
{properties_rows}
""",
        encoding="utf-8",
    )
    return path


class TestParserDecodesProperties:
    def test_properties_reach_record_attributes_typed_via_attribute_types(self, tmp_path: Path) -> None:
        path = _write_entity(
            tmp_path,
            attribute_types="  investment_level: integer\n",
            properties_rows="| investment_level | 4 |\n| Owner | Platform Team |",
        )
        record = parse_entity(path, tmp_path / "model", domain_names=_DOMAINS)
        assert record is not None
        assert record.attributes["investment_level"] == 4
        assert record.attributes["Owner"] == "Platform Team"

    def test_untyped_cells_decode_leniently_as_strings(self, tmp_path: Path) -> None:
        path = _write_entity(tmp_path, properties_rows="| investment_level | 4 |")
        record = parse_entity(path, tmp_path / "model", domain_names=_DOMAINS)
        assert record is not None
        # Lenient decode without a declared type; numeric consumers coerce.
        assert str(record.attributes["investment_level"]) == "4"

    def test_entity_without_properties_has_empty_attributes(self, tmp_path: Path) -> None:
        model_root = tmp_path / "model"
        path = model_root / "strategy" / "capability" / "CAP@1.abc.plain.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nartifact-id: CAP@1.abc.plain\nartifact-type: capability\nname: Plain\n"
            "version: 0.1.0\nstatus: active\n---\n\n<!-- §content -->\n\n## Plain\n\nBody.\n",
            encoding="utf-8",
        )
        record = parse_entity(path, model_root, domain_names=_DOMAINS)
        assert record is not None
        assert dict(record.attributes) == {}
        assert record.extra == {}


class TestAttributeReads:
    def test_attributes_win_over_frontmatter_extra(self, tmp_path: Path) -> None:
        path = _write_entity(
            tmp_path,
            attribute_types="  investment_level: integer\n",
            properties_rows="| investment_level | 4 |",
        )
        record = parse_entity(path, tmp_path / "model", domain_names=_DOMAINS)
        assert record is not None
        value, present = read_attribute_value(record, "investment_level", context="entity")
        assert present
        assert value == 4

    def test_frontmatter_extra_remains_the_fallback(self, tmp_path: Path) -> None:
        model_root = tmp_path / "model"
        path = model_root / "strategy" / "resource" / "RES@1.abc.frontmatter-only.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nartifact-id: RES@1.abc.frontmatter-only\nartifact-type: resource\nname: F\n"
            "version: 0.1.0\nstatus: active\ncustom-flag: enabled\n---\n\n<!-- §content -->\n\n## F\n\nBody.\n",
            encoding="utf-8",
        )
        record = parse_entity(path, model_root, domain_names=_DOMAINS)
        assert record is not None
        value, present = read_attribute_value(record, "custom-flag", context="entity")
        assert present
        assert value == "enabled"
