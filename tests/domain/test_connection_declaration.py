"""Unit + property tests for the unified connection-declaration grammar.

Behavior-preserving replacement for the private header regexes formerly
duplicated in artifact_parsing.py, parse_existing.py, artifact_write_formatting.py,
and _verifier_outgoing.py.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from src.domain.repository.connection_declaration import (
    ConnectionDeclaration,
    format_connection_declaration,
    parse_connection_declarations,
    parse_connection_header,
)

_CONN_TYPE = st.from_regex(r"[a-z][a-z0-9-]{1,12}", fullmatch=True)
_MULTIPLICITY = st.sampled_from(["", "0", "1", "0..1", "1..*", "0..*", "*"])
_TARGET_ID = st.from_regex(r"[A-Za-z][A-Za-z0-9@._-]{1,20}", fullmatch=True)
_DESCRIPTION = st.text(
    alphabet=st.characters(exclude_categories=("Cc", "Cs"), exclude_characters="#<>"),
    max_size=40,
).map(lambda s: s.strip())
_ASSOC_IDS = st.lists(_TARGET_ID, max_size=3, unique=True).map(tuple)
_SLUG = st.from_regex(r"[a-z][a-z0-9-]{1,12}", fullmatch=True)
_METADATA = st.one_of(
    st.just({}),
    _SLUG.map(lambda slug: {"specialization": slug}),
)


def _assemble(decls: list[ConnectionDeclaration]) -> str:
    """Mirror format_outgoing_markdown's section-joining idiom (blank line + header block)."""
    sections: list[str] = []
    for decl in decls:
        sections.append("")
        sections.append(format_connection_declaration(decl))
    return "\n".join(sections)


class TestParseConnectionHeader:
    def test_valid_header_no_multiplicity(self) -> None:
        decl = parse_connection_header("archimate-realization → REQ@2.B.tgt")
        assert decl == ConnectionDeclaration(conn_type="archimate-realization", target_id="REQ@2.B.tgt")

    def test_valid_header_both_multiplicities(self) -> None:
        decl = parse_connection_header("archimate-aggregation [1] → [0..*] REQ@2.B.tgt")
        assert decl is not None
        assert decl.src_multiplicity == "1"
        assert decl.tgt_multiplicity == "0..*"
        assert decl.target_id == "REQ@2.B.tgt"

    def test_malformed_header_missing_arrow(self) -> None:
        assert parse_connection_header("archimate-realization REQ@2.B.tgt") is None

    def test_malformed_header_empty(self) -> None:
        assert parse_connection_header("") is None


class TestParseConnectionDeclarations:
    def test_multiple_sections_with_assoc_and_description(self) -> None:
        text = (
            "\n### archimate-realization [1] → [0..*] REQ@2.B.tgt\n\n"
            "Realizes the target requirement.\n"
            "<!-- §assoc STK@1.A.stakeholder -->\n"
            "\n### archimate-serving → APP@3.C.svc\n"
        )
        decls = parse_connection_declarations(text)
        assert [d.conn_type for d in decls] == ["archimate-realization", "archimate-serving"]
        assert decls[0].description == "Realizes the target requirement."
        assert decls[0].associated_entities == ("STK@1.A.stakeholder",)
        assert decls[1].description == ""
        assert decls[1].associated_entities == ()

    def test_malformed_section_skipped(self) -> None:
        text = "\n### not a valid header\n\nsome body\n\n### archimate-serving → APP@3.C.svc\n"
        decls = parse_connection_declarations(text)
        assert len(decls) == 1
        assert decls[0].conn_type == "archimate-serving"


class TestFormatConnectionDeclaration:
    def test_header_only(self) -> None:
        decl = ConnectionDeclaration(conn_type="archimate-serving", target_id="APP@3.C.svc")
        assert format_connection_declaration(decl) == "### archimate-serving → APP@3.C.svc"

    def test_with_multiplicities_description_and_assoc(self) -> None:
        decl = ConnectionDeclaration(
            conn_type="archimate-aggregation",
            target_id="REQ@2.B.tgt",
            src_multiplicity="1",
            tgt_multiplicity="0..*",
            description="Prose.",
            associated_entities=("STK@1.A.stakeholder",),
        )
        formatted = format_connection_declaration(decl)
        assert formatted == (
            "### archimate-aggregation [1] → [0..*] REQ@2.B.tgt\n\n"
            "Prose.\n"
            "<!-- §assoc STK@1.A.stakeholder -->"
        )


class TestRoundTrip:
    """Behavior-preserving property test for the connection-declaration grammar.

    Covers the per-connection metadata block too: a shared round-trip
    test for both known kinds of section content, not a separate test file per kind.
    """

    @given(
        st.lists(
            st.builds(
                ConnectionDeclaration,
                conn_type=_CONN_TYPE,
                target_id=_TARGET_ID,
                src_multiplicity=_MULTIPLICITY,
                tgt_multiplicity=_MULTIPLICITY,
                description=_DESCRIPTION,
                associated_entities=_ASSOC_IDS,
                metadata=_METADATA,
            ),
            max_size=5,
        )
    )
    def test_format_then_parse_round_trips(self, decls: list[ConnectionDeclaration]) -> None:
        text = _assemble(decls)
        parsed = parse_connection_declarations(text)
        assert len(parsed) == len(decls)
        for original, recovered in zip(decls, parsed, strict=True):
            assert recovered.conn_type == original.conn_type
            assert recovered.target_id == original.target_id
            assert recovered.src_multiplicity == original.src_multiplicity
            assert recovered.tgt_multiplicity == original.tgt_multiplicity
            assert recovered.description == original.description
            assert recovered.associated_entities == original.associated_entities
            assert recovered.metadata == original.metadata


class TestMetadataBlock:
    def test_format_includes_fenced_yaml_block(self) -> None:
        decl = ConnectionDeclaration(
            conn_type="archimate-flow",
            target_id="APP@1.a.tgt",
            metadata={"specialization": "money-flow"},
        )
        formatted = format_connection_declaration(decl)
        assert formatted == (
            "### archimate-flow → APP@1.a.tgt\n\n```yaml\nspecialization: money-flow\n```"
        )

    def test_parse_recovers_metadata_and_leaves_description_intact(self) -> None:
        text = (
            "\n### archimate-flow → APP@1.a.tgt\n\n"
            "```yaml\nspecialization: money-flow\n```\n\n"
            "Prose description follows.\n"
        )
        (decl,) = parse_connection_declarations(text)
        assert decl.metadata == {"specialization": "money-flow"}
        assert decl.description == "Prose description follows."

    def test_two_sections_carry_different_metadata(self) -> None:
        a = ConnectionDeclaration(
            conn_type="archimate-flow", target_id="APP@1.a.one", metadata={"specialization": "money-flow"}
        )
        b = ConnectionDeclaration(conn_type="archimate-assignment", target_id="APP@1.a.two")
        parsed = parse_connection_declarations(_assemble([a, b]))
        assert parsed[0].metadata == {"specialization": "money-flow"}
        assert parsed[1].metadata == {}

    def test_malformed_metadata_block_falls_back_to_body_text(self) -> None:
        text = "\n### archimate-flow → APP@1.a.tgt\n\n```yaml\n[unterminated\n```\n"
        (decl,) = parse_connection_declarations(text)
        assert decl.metadata == {}
        assert "```yaml" in decl.description

    def test_no_metadata_block_is_absent_from_output(self) -> None:
        decl = ConnectionDeclaration(conn_type="archimate-serving", target_id="APP@1.a.tgt")
        assert "```" not in format_connection_declaration(decl)
