"""A purpose line reads back as the lines that were written — on a diagram and on a viewpoint alike.

The writer and the reader are held as a pair, over what the syntax permits rather than what any surface
writes today: prose of any wording (including text that looks like a reference, a list marker, a YAML
keyword or a comment), references in either id spelling, and either list empty. The pair is exercised
through the frontmatter text a diagram file holds, and through a viewpoint definition's mapping.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.application.modeling.diagram_file_format import format_diagram_puml
from src.domain.purpose_lines import (
    MalformedPurposeLine,
    Prose,
    PurposeLines,
    Reference,
    purpose_lines_as_written,
    read_purpose_lines,
)
from src.domain.repository.frontmatter import parse_frontmatter
from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.domain.viewpoints.viewpoint_serialization import viewpoint_definition_to_mapping

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_TRICKY = st.sampled_from(["ref: STK@1.abc", "- a", "# not a comment", "yes", "null", "{ref: x}", "'quoted'", "a: b"])
_prose = (st.text(min_size=1, max_size=40).map(str.strip).filter(bool) | _TRICKY).map(Prose)
_ids = st.builds(
    lambda prefix, epoch, random, slug: f"{prefix}@{epoch}.{random}" + (f".{slug}" if slug else ""),
    st.sampled_from(["STK", "GOL", "DRV", "REQ"]),
    st.integers(1_000_000_000, 1_999_999_999),
    st.text(_LETTERS, min_size=6, max_size=6),
    st.none() | st.from_regex(r"[a-z][a-z0-9-]{0,12}[a-z0-9]", fullmatch=True),
)
_entries = st.lists(_prose | _ids.map(Reference), max_size=5).map(tuple)
_lines = st.builds(PurposeLines, stakeholders=_entries, concerns=_entries)


def _diagram_text(lines: PurposeLines) -> str:
    return format_diagram_puml(
        artifact_id="ARC@1700000000.aaaaaa.purpose", diagram_type="archimate-motivation", name="Purpose",
        version="0.1.0", status="draft", last_updated="2026-11-27T00:00:00Z", puml_body="@startuml\n@enduml\n",
        purpose_lines=lines,
    )


@given(_lines)
def test_a_diagram_reads_back_the_lines_written_into_it(lines: PurposeLines) -> None:
    frontmatter = parse_frontmatter(_diagram_text(lines))

    assert read_purpose_lines(frontmatter) == lines


@given(_lines)
def test_a_viewpoint_reads_back_the_lines_written_into_it(lines: PurposeLines) -> None:
    written = viewpoint_definition_to_mapping(
        viewpoint_definition_from_mapping({"slug": "probe", "name": "Probe", **purpose_lines_as_written(lines)})
    )

    assert viewpoint_definition_from_mapping(written).purpose_lines == lines


@given(_lines)
def test_an_empty_list_is_not_written(lines: PurposeLines) -> None:
    written = purpose_lines_as_written(lines)

    assert ("stakeholders" in written) == bool(lines.stakeholders)
    assert ("concerns" in written) == bool(lines.concerns)


def test_a_viewpoint_stating_plain_strings_reads_them_as_prose() -> None:
    """The form every viewpoint was written in before references existed: unchanged, and prose."""
    definition = viewpoint_definition_from_mapping(
        {"slug": "legacy", "stakeholders": ["Enterprise Architects", "managers"], "concerns": ["cost"]}
    )

    assert definition.stakeholders == (Prose("Enterprise Architects"), Prose("managers"))
    assert definition.concerns == (Prose("cost"),)
    assert viewpoint_definition_to_mapping(definition)["stakeholders"] == ["Enterprise Architects", "managers"]


@pytest.mark.parametrize(
    "stated",
    [
        {"stakeholders": "Operations"},
        {"stakeholders": [""]},
        {"stakeholders": ["  "]},
        {"concerns": [{"ref": ""}]},
        {"concerns": [{"ref": 7}]},
        {"concerns": [{"ref": "GOL@1.a", "text": "extra"}]},
        {"concerns": [{"name": "GOL@1.a"}]},
        {"stakeholders": [3]},
        {"stakeholders": {"ref": "STK@1.a"}},
    ],
)
def test_what_is_not_a_purpose_line_is_refused_with_a_sentence(stated: dict[str, object]) -> None:
    with pytest.raises(MalformedPurposeLine) as refusal:
        read_purpose_lines(stated)

    assert str(refusal.value)


def test_a_diagram_inherits_each_list_it_does_not_state() -> None:
    own = PurposeLines(stakeholders=(Prose("Operations"),))
    viewpoint = PurposeLines(stakeholders=(Prose("Architects"),), concerns=(Reference("GOL@1.aaaaaa"),))

    assert own.over(viewpoint) == PurposeLines(stakeholders=(Prose("Operations"),), concerns=viewpoint.concerns)
    assert PurposeLines().over(viewpoint) == viewpoint
    assert viewpoint.over(PurposeLines()) == viewpoint


def test_a_reference_is_found_in_either_id_spelling() -> None:
    lines = PurposeLines(stakeholders=(Reference("STK@1700000000.aBcDeF.operations"),))

    assert lines.names("STK@1700000000.aBcDeF")
    assert lines.names("STK@1700000000.aBcDeF.renamed")
    assert not lines.names("STK@1700000000.zzzzzz")


def test_an_edit_replaces_only_the_lists_it_names() -> None:
    stored = PurposeLines(stakeholders=(Prose("Operations"),), concerns=(Prose("cost"),))

    assert stored.restated(stakeholders=None, concerns=[{"ref": "GOL@1.aaaaaa"}]) == PurposeLines(
        stakeholders=(Prose("Operations"),), concerns=(Reference("GOL@1.aaaaaa"),)
    )
    assert stored.restated(stakeholders=[], concerns=None) == PurposeLines(concerns=(Prose("cost"),))
