"""Integration tests for typed-property round-trips (WU-B3).

Covers:
- Typed values round-trip through format_entity_markdown → parse → decode_entity_properties
- attribute-types key is persisted in entity frontmatter
- E042 blocking error emitted when ad-hoc type fails to decode
- W042 warning emitted for schema constraint violations (schema file on disk)
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_parsing import decode_entity_properties
from src.application.modeling.artifact_write_formatting import format_entity_markdown
from src.application.verification._verifier_rules_schema import check_attribute_schema
from src.application.verification.artifact_verifier_types import VerificationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_entity(
    path: Path,
    *,
    artifact_type: str = "requirement",
    properties: dict | None = None,
    attribute_types: dict[str, str] | None = None,
) -> str:
    content = format_entity_markdown(
        artifact_id="REQ@1.t.test",
        artifact_type=artifact_type,
        name="Test Entity",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        keywords=None,
        summary="Test summary",
        properties=properties,
        attribute_types=attribute_types,
        notes=None,
        display_section_id="disp",
        display_content=(
            "### archimate\n\n```yaml\ndomain: Motivation\n"
            "element-type: Requirement\nlabel: Test Entity\nalias: REQ_test\n```"
        ),
        repo_root=path.parent,
    )
    path.write_text(content, encoding="utf-8")
    return content


_FAKE_PATH = Path("/tmp/entity.md")


def _fresh_result() -> VerificationResult:
    return VerificationResult(path=_FAKE_PATH, file_type="entity")


def _write_schema(repo_root: Path, artifact_type: str, schema: dict) -> None:
    schemata_dir = repo_root / ".arch-repo" / "schemata"
    schemata_dir.mkdir(parents=True, exist_ok=True)
    (schemata_dir / f"attributes.{artifact_type}.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Round-trip: typed values survive format → parse → decode
# ---------------------------------------------------------------------------


class TestTypedPropertyRoundTrip:
    def test_integer_survives_roundtrip(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Count": 42},
            attribute_types={"Count": "integer"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        result = decode_entity_properties(raw_props, {}, {"Count": "integer"})
        assert result["Count"] == 42
        assert isinstance(result["Count"], int)

    def test_boolean_survives_roundtrip(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Enabled": True},
            attribute_types={"Enabled": "boolean"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        result = decode_entity_properties(raw_props, {}, {"Enabled": "boolean"})
        assert result["Enabled"] is True

    def test_number_survives_roundtrip(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Score": 3.14},
            attribute_types={"Score": "number"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        result = decode_entity_properties(raw_props, {}, {"Score": "number"})
        assert abs(result["Score"] - 3.14) < 1e-9

    def test_string_property_preserved_without_type(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Note": "hello world"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        result = decode_entity_properties(raw_props, {}, {})
        assert result["Note"] == "hello world"

    def test_array_of_strings_survives_roundtrip(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Tags": ["a", "b", "c"]},
            attribute_types={"Tags": "array"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        result = decode_entity_properties(raw_props, {}, {"Tags": "array"})
        assert result["Tags"] == ["a", "b", "c"]

    def test_schema_type_takes_precedence_over_adhoc(self, tmp_path: Path) -> None:
        from src.application.artifact_parsing import parse_entity_content_sections

        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Count": 7},
            attribute_types={"Count": "integer"},
        )
        parsed = parse_entity_content_sections(content)
        raw_props: dict[str, str] = parsed["properties"]
        # Schema declares Count as integer; adhoc also says integer — both agree
        prop_schemata = {"Count": {"type": "integer"}}
        result = decode_entity_properties(raw_props, prop_schemata, {"Count": "integer"})
        assert result["Count"] == 7
        assert isinstance(result["Count"], int)


# ---------------------------------------------------------------------------
# attribute-types key persisted in frontmatter
# ---------------------------------------------------------------------------


class TestAttributeTypesFrontmatter:
    def test_attribute_types_written_to_frontmatter(self, tmp_path: Path) -> None:
        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Count": 1, "Enabled": True},
            attribute_types={"Count": "integer", "Enabled": "boolean"},
        )
        assert "attribute-types:" in content
        assert "Count: integer" in content
        assert "Enabled: boolean" in content

    def test_no_attribute_types_key_when_none(self, tmp_path: Path) -> None:
        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Note": "value"},
            attribute_types=None,
        )
        assert "attribute-types:" not in content

    def test_attribute_types_in_frontmatter_position(self, tmp_path: Path) -> None:
        content = _write_entity(
            tmp_path / "entity.md",
            properties={"Count": 42},
            attribute_types={"Count": "integer"},
        )
        # attribute-types must appear before the §content section
        fm_end = content.index("---", content.index("---") + 3)
        attr_pos = content.index("attribute-types:", 0)
        assert attr_pos < fm_end


# ---------------------------------------------------------------------------
# E042 blocking: ad-hoc type decode failure
# ---------------------------------------------------------------------------


class TestE042DecodeError:
    # check_attribute_schema only runs when a schema file exists for the type.
    # These tests use "typed-test" with a minimal schema so the ad-hoc decode
    # path (attribute-types frontmatter) is exercised.

    def test_bad_integer_cell_emits_e042(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "typed-test", {"type": "object"})
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Count": "not-a-number"},
            attribute_types={"Count": "integer"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Count": "integer"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        codes = [i.code for i in result.issues]
        assert "E042" in codes

    def test_e042_is_severity_error(self, tmp_path: Path) -> None:
        from src.application.verification.artifact_verifier_types import Severity

        _write_schema(tmp_path, "typed-test", {"type": "object"})
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Enabled": "yes"},  # not a valid boolean
            attribute_types={"Enabled": "boolean"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Enabled": "boolean"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        e042 = [i for i in result.issues if i.code == "E042"]
        assert e042
        assert e042[0].severity == Severity.ERROR

    def test_valid_integer_emits_no_e042(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "typed-test", {"type": "object"})
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Count": 5},
            attribute_types={"Count": "integer"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Count": "integer"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        codes = [i.code for i in result.issues]
        assert "E042" not in codes


# ---------------------------------------------------------------------------
# W042 warning: schema constraint violation (schema file on disk)
# ---------------------------------------------------------------------------


class TestW042ConstraintViolation:
    def test_value_below_minimum_emits_w042(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "typed-test", {
            "type": "object",
            "properties": {"Count": {"type": "integer", "minimum": 1}},
        })
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Count": 0},
            attribute_types={"Count": "integer"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Count": "integer"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        codes = [i.code for i in result.issues]
        assert "W042" in codes
        assert "E042" not in codes

    def test_w042_is_severity_warning(self, tmp_path: Path) -> None:
        from src.application.verification.artifact_verifier_types import Severity

        _write_schema(tmp_path, "typed-test", {
            "type": "object",
            "properties": {"Count": {"type": "integer", "minimum": 1}},
        })
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Count": 0},
            attribute_types={"Count": "integer"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Count": "integer"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        w042 = [i for i in result.issues if i.code == "W042"]
        assert w042
        assert w042[0].severity == Severity.WARNING

    def test_valid_value_emits_no_w042(self, tmp_path: Path) -> None:
        _write_schema(tmp_path, "typed-test", {
            "type": "object",
            "properties": {"Count": {"type": "integer", "minimum": 1}},
        })
        content = _write_entity(
            tmp_path / "entity.md",
            artifact_type="typed-test",
            properties={"Count": 5},
            attribute_types={"Count": "integer"},
        )
        fm = {"artifact-type": "typed-test", "attribute-types": {"Count": "integer"}}
        result = _fresh_result()
        check_attribute_schema(content, fm, tmp_path, result, "test")
        codes = [i.code for i in result.issues]
        assert "W042" not in codes
        assert "E042" not in codes
