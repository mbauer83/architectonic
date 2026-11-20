"""An entity's Properties section reads back what was written into it, through every reader it has.

The writer escaped a pipe in a value from the day the typed codec arrived, and none of the three
readers could see past the escape: the index and the editor cut the value at the pipe, the verifier
then dropped the backslash's cell and validated what was left. The same two also took any row holding
three hyphens — a connection id, a dash in prose — for the delimiter row, and any attribute named
`Attribute` for the header. Each case below is one of those, stated as a value the syntax permits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.parsing import parse_entity_content_sections
from src.application.modeling.artifact_write_formatting import format_entity_markdown
from src.application.verification._verifier_rules_schema import stated_properties
from src.domain.ontology_representation.property_value import PropertyValue, decode, encode
from src.domain.repository.properties_section import format_properties_section, read_properties
from src.infrastructure.write.artifact_write.parse_existing import parse_entity_file

_PERMITTED_VALUES = (
    "plain",
    "a|b",
    "ends in a pipe|",
    "back\\slash",
    "ends in a backslash\\",
    "a backslash then a pipe \\|",
    "ENT@1.a.source---ENT@2.b.target",
    "a dash --- in prose",
    "two\nlines",
    "two\r\nwindows lines",
    "a lone\rcarriage return",
    "a line\u2028separator and a form\x0cfeed",
    "a literal \\r and a literal \\n",
    "`code | span`",
    "[a link|with a pipe](target.md)",
)

_PERMITTED_NAMES = ("owner", "Attribute", "a|b", "back\\slash", "dashed---name")


def _section(properties: dict[str, str]) -> str:
    return "\n".join(format_properties_section((name, encode(value)) for name, value in properties.items()))


class TestTheSectionRoundTrips:
    @pytest.mark.parametrize("value", _PERMITTED_VALUES)
    def test_a_value_reads_back(self, value: str) -> None:
        read = read_properties(_section({"first": value, "second": "after"}))

        assert read is not None
        assert {name: decode(cell, "string") for name, cell in read.items()} == {"first": value, "second": "after"}

    @pytest.mark.parametrize("name", _PERMITTED_NAMES)
    def test_an_attribute_name_reads_back(self, name: str) -> None:
        assert read_properties(_section({name: "value"})) == {name: "value"}

    @pytest.mark.parametrize("value", [3, 2.5, True, ["a|b", "c"]])
    def test_a_typed_value_reads_back(self, value: PropertyValue) -> None:
        kind = {int: "integer", float: "number", bool: "boolean", list: "array"}[type(value)]
        read = read_properties("\n".join(format_properties_section([("typed", encode(value))])))

        assert read is not None
        assert decode(read["typed"], kind) == value

    @pytest.mark.parametrize("name", ["two\nlines", "two\r\nlines", "two\rlines"])
    def test_a_name_of_several_lines_is_refused_by_name(self, name: str) -> None:
        with pytest.raises(ValueError, match="an attribute name is one line") as refusal:
            format_properties_section([(name, "value")])

        assert repr(name) in str(refusal.value)

    def test_an_unfilled_attribute_is_stated_empty(self) -> None:
        assert read_properties("\n".join(format_properties_section([("owner", "x"), ("tier", "")]))) == {
            "owner": "x",
            "tier": "",
        }

    def test_an_entity_without_properties_states_none(self) -> None:
        section = format_properties_section([])

        assert section[-1] == "| (none) | (none) |"
        assert read_properties("\n".join(section)) == {}

    def test_a_text_without_the_section_has_no_properties_to_read(self) -> None:
        assert read_properties("## Name\n\n| Attribute | Value |\n|---|---|\n| a | b |\n") is None

    def test_the_section_ends_at_the_next_one(self) -> None:
        text = _section({"owner": "x"}) + "\n\n## Notes\n\n| Attribute | Value |\n|---|---|\n| stray | y |\n"

        assert read_properties(text) == {"owner": "x"}


class TestEveryReaderOfAWrittenEntityAgrees:
    """The pair that was never tested: the product's writer against each of its three readers."""

    @pytest.fixture
    def written(self, tmp_path: Path) -> tuple[Path, dict[str, str]]:
        properties = {f"p{at}": value for at, value in enumerate(_PERMITTED_VALUES)} | {"Attribute": "named so"}
        content = format_entity_markdown(
            artifact_id="CAP@1.aaaaaa.example",
            artifact_type="capability",
            name="Example",
            version="0.1.0",
            status="draft",
            last_updated="2026-01-01",
            keywords=None,
            summary="An example.",
            properties=dict(properties),
            notes=None,
            display_section_id="archimate",
            display_content="label: Example",
        )
        path = tmp_path / "CAP@1.aaaaaa.example.md"
        path.write_text(content, encoding="utf-8")
        return path, properties

    def test_the_index_reads_what_was_written(self, written: tuple[Path, dict[str, str]]) -> None:
        path, properties = written
        cells = parse_entity_content_sections(path.read_text(encoding="utf-8"))["properties"]

        assert {name: decode(cell, "string") for name, cell in cells.items()} == properties

    def test_the_editor_reads_what_was_written(self, written: tuple[Path, dict[str, str]]) -> None:
        path, properties = written
        cells = parse_entity_file(path).properties

        assert {name: decode(cell, "string") for name, cell in cells.items()} == properties

    def test_the_verifier_reads_what_was_written(self, written: tuple[Path, dict[str, str]]) -> None:
        path, properties = written
        cells = stated_properties(path.read_text(encoding="utf-8"))

        assert cells is not None
        assert {name: decode(cell, "string") for name, cell in cells.items()} == properties

    def test_the_verifier_is_not_asked_about_an_unfilled_attribute(self) -> None:
        text = "\n".join(format_properties_section([("owner", "x"), ("tier", "")]))

        assert stated_properties(text) == {"owner": "x"}
