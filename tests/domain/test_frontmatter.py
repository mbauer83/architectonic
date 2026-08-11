"""One definition of the frontmatter block, and it is the tolerant one.

Fourteen sites decided this independently, in five families that did not agree. The two loosest were the
*verifier* and the document write path — `startswith("---")` plus `find("\\n---", 3)` — which accept
`----`, accept `---anything` as an opening fence, and find a closing fence inside a YAML value. The
strictest required a newline after the closing fence, so a file ending exactly `---` had no frontmatter
at all.

`rendering/puml_safety`'s reading was a superset of the rest and is what the domain now holds. These
tests pin the behaviour that made it the right one to keep, and the cases where the old readings
disagreed.

Every input is authored here, so exact assertions are the test's own.
"""

from __future__ import annotations

import pytest

from src.domain.repository.frontmatter import (
    Frontmatter,
    FrontmatterProblem,
    body_after_frontmatter,
    opens_with_frontmatter,
    parse_frontmatter,
    read_frontmatter,
    replace_frontmatter_text,
)

SIMPLE = "---\nartifact-id: ENT@1.aa\nname: Thing\n---\nbody text\n"


class TestReadingABlock:
    def test_it_returns_the_yaml_without_either_fence(self) -> None:
        reading = read_frontmatter(SIMPLE)

        assert isinstance(reading, Frontmatter)
        assert reading.text == "artifact-id: ENT@1.aa\nname: Thing"
        assert reading.body == "body text\n"

    def test_end_is_where_the_body_begins(self) -> None:
        reading = read_frontmatter(SIMPLE)

        assert isinstance(reading, Frontmatter)
        assert SIMPLE[reading.end :] == reading.body

    def test_a_block_holding_only_a_blank_line_is_a_block(self) -> None:
        reading = read_frontmatter("---\n\n---\nbody\n")

        assert isinstance(reading, Frontmatter)
        assert reading.text == ""
        assert reading.body == "body\n"

    def test_a_zero_length_block_is_a_block(self) -> None:
        """`---\\n---\\n` with nothing between the fences, which a diagram writes before its keys exist.

        Caught by `test_cascade_delete` during the unification: requiring a line ending *before* the
        closing fence read this as unterminated and lost the file's frontmatter entirely, so the content
        group is optional.
        """
        reading = read_frontmatter("---\n---\n@startuml\n@enduml\n")

        assert isinstance(reading, Frontmatter)
        assert reading.text == ""
        assert reading.body == "@startuml\n@enduml\n"

    def test_the_first_closing_fence_wins(self) -> None:
        """Non-greedy: a `---` later in the body does not extend the block over it."""
        reading = read_frontmatter("---\na: 1\n---\nbody\n---\nnot frontmatter\n")

        assert isinstance(reading, Frontmatter)
        assert reading.text == "a: 1"
        assert reading.body == "body\n---\nnot frontmatter\n"


class TestWhatTheOldReadingsDisagreedAbout:
    def test_a_block_may_end_the_file_with_no_trailing_newline(self) -> None:
        """Four of the five old readings required `\\n` after the closing fence and found nothing here."""
        reading = read_frontmatter("---\na: 1\n---")

        assert isinstance(reading, Frontmatter)
        assert reading.text == "a: 1"
        assert reading.body == ""

    @pytest.mark.parametrize("fenced", ["---  \na: 1\n---\n", "---\na: 1\n---  \n", "---\t\na: 1\n---\t\n"])
    def test_trailing_whitespace_on_either_fence_is_tolerated(self, fenced: str) -> None:
        """Only one old reading tolerated this; a stray space made the file frontmatter-less."""
        reading = read_frontmatter(fenced)

        assert isinstance(reading, Frontmatter)
        assert reading.text == "a: 1"

    def test_crlf_line_endings_are_read(self) -> None:
        reading = read_frontmatter("---\r\na: 1\r\n---\r\nbody\r\n")

        assert isinstance(reading, Frontmatter)
        assert reading.text == "a: 1"
        assert reading.body == "body\r\n"

    def test_a_four_dash_line_is_not_a_fence(self) -> None:
        """`startswith("---")` accepted this and treated `-` as the first YAML character."""
        assert read_frontmatter("----\na: 1\n---\n") is FrontmatterProblem.NO_OPENING_FENCE

    def test_text_after_the_opening_dashes_is_not_a_fence(self) -> None:
        """`startswith("---")` accepted `---yaml` and silently parsed from character 3."""
        assert read_frontmatter("---yaml\na: 1\n---\n") is FrontmatterProblem.NO_OPENING_FENCE

    def test_a_closing_fence_with_trailing_text_does_not_close_the_block(self) -> None:
        """`find("\\n---", 3)` stopped at `\\n---more`, cutting the block short."""
        assert read_frontmatter("---\na: 1\n---more\n") is FrontmatterProblem.NO_CLOSING_FENCE


class TestTheTwoProblemsStayApart:
    def test_no_opening_fence(self) -> None:
        assert read_frontmatter("just a body\n") is FrontmatterProblem.NO_OPENING_FENCE

    def test_an_opening_fence_that_is_never_closed(self) -> None:
        """The verifier reports this as E012 and the missing opening as E011, so they must differ."""
        assert read_frontmatter("---\na: 1\nno closing fence\n") is FrontmatterProblem.NO_CLOSING_FENCE

    def test_the_two_problems_are_not_equal(self) -> None:
        assert FrontmatterProblem.NO_OPENING_FENCE is not FrontmatterProblem.NO_CLOSING_FENCE


class TestParseFrontmatter:
    def test_it_returns_the_mapping(self) -> None:
        assert parse_frontmatter(SIMPLE) == {"artifact-id": "ENT@1.aa", "name": "Thing"}

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("no frontmatter\n", id="absent"),
            pytest.param("---\na: 1\nunclosed\n", id="unterminated"),
            pytest.param("---\n\n---\nbody\n", id="empty-block"),
            pytest.param("---\n- 1\n- 2\n---\nbody\n", id="sequence-not-mapping"),
            pytest.param("---\njust a scalar\n---\nbody\n", id="scalar-not-mapping"),
        ],
    )
    def test_anything_that_is_not_a_mapping_answers_empty(self, source: str) -> None:
        """Callers each defaulted to `{}` for these; the primitive does it once rather than five ways."""
        assert parse_frontmatter(source) == {}

    def test_it_does_not_distinguish_an_absent_block_from_an_empty_one(self) -> None:
        """Stated as a test because it is the reason `read_frontmatter` exists beside this.

        `application/artifacts/parsing.extract_yaml_block` needs `None` for "no readable block" and `{}`
        for "block present but empty" — the unrecognized-structure upgrade step reports a malformed block
        on the first and falls through to its artifact-type checks on the second. Routing that caller
        through `parse_frontmatter` collapsed the two and broke the step, so it reads the block itself.
        """
        assert parse_frontmatter("no fence at all\n") == parse_frontmatter("---\n---\nbody\n") == {}


class TestBodyAfterFrontmatter:
    def test_it_strips_the_block(self) -> None:
        assert body_after_frontmatter(SIMPLE) == "body text\n"

    def test_a_source_with_no_block_is_returned_unchanged(self) -> None:
        assert body_after_frontmatter("@startuml\nA -> B\n@enduml\n") == "@startuml\nA -> B\n@enduml\n"

    def test_an_unterminated_block_is_left_alone_rather_than_half_stripped(self) -> None:
        source = "---\na: 1\nnever closed\n"
        assert body_after_frontmatter(source) == source


class TestReplaceFrontmatterText:
    def test_it_swaps_the_yaml_and_keeps_the_body(self) -> None:
        assert replace_frontmatter_text(SIMPLE, "name: Other") == "---\nname: Other\n---\nbody text\n"

    def test_it_leaves_both_fences_exactly_as_authored(self) -> None:
        """A re-pin changes one field; it must not normalise the file's line endings or fence spacing."""
        source = "---  \r\na: 1\r\n---  \r\nbody\r\n"

        assert replace_frontmatter_text(source, "a: 2") == "---  \r\na: 2\r\n---  \r\nbody\r\n"

    def test_a_source_with_no_block_is_returned_unchanged(self) -> None:
        assert replace_frontmatter_text("no block\n", "a: 1") == "no block\n"


class TestOpensWithFrontmatter:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            pytest.param("---\na: 1\n---\n", True, id="complete-block"),
            pytest.param("---\nnever closed\n", True, id="opening-only"),
            pytest.param("---  \na: 1\n---\n", True, id="trailing-space-on-fence"),
            pytest.param("---\r\na: 1\r\n---\r\n", True, id="crlf"),
            pytest.param("----\na: 1\n---\n", False, id="four-dashes"),
            pytest.param("---yaml\na: 1\n---\n", False, id="text-after-dashes"),
            pytest.param("body only\n", False, id="no-fence"),
            pytest.param("", False, id="empty-file"),
        ],
    )
    def test_it_recognises_a_fence_and_only_a_fence(self, source: str, expected: bool) -> None:
        assert opens_with_frontmatter(source) is expected
