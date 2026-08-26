"""Restyling a declaration leaves it declaring exactly what it declared.

The round trip this project requires of any syntax it both writes and reads — and the one syntax where
it has already been paid for. Five modules once disagreed about what declares an alias, and the sharpest
disagreement was **whether a trailing `#colour` still declares one**: three of the five anchored the
alias to the end of the line, so a body drawing `circle " " as JNA_x #252327` lost that junction from
`entity-ids-used` and both its connections from `connection-ids-used`, and E315 then objected to an alias
the writer had dropped. The same body without the colour verified clean.

An ad-hoc reading lens now *writes* that colour, and appends to labels. So this asserts the pair rather
than either side: restyle a declaration, read the body back with `declared_aliases`, and require the same
aliases in the same order.

**Stated over what the syntax permits, not over what the renderer emits today.** The plan's own rule,
and the reason the first version of a comparable gate passed against a broken reading: the shipped
specialization catalogue happens to declare no colours, so a round trip exercised only against emitted
bodies would have proved nothing about the case that broke. Every form the owner's docstring names has a
case here — a trailing colour, a label containing the word `as`, a hyphenated alias, a line opening a
block, a sprite, a stereotype, a macro call, and a relation that declares nothing.
"""

from __future__ import annotations

import pytest

from src.application.puml_alias_declarations import (
    declared_aliases,
    restyled_declaration,
)

#: Every declaration form the owner's docstring names, plus the lines that must not be touched.
_FORMS = [
    ('rectangle "Plain" <<capability>> as CAP_a', "CAP_a"),
    ('rectangle "Already coloured" <<capability>> as CAP_b #EFBD5D', "CAP_b"),
    ('rectangle "Compound colour" as CAP_c #back:EFBD5D;line:48391C;text:252327', "CAP_c"),
    ('circle " " as JNA_x #252327', "JNA_x"),
    ('rectangle "AI-Assisted Development as Dominant Production Mode" as DRV_q', "DRV_q"),
    ('rectangle "Hyphenated" as CAP-with-hyphen', "CAP-with-hyphen"),
    ('rectangle "Opens a block" <<StrategyGrouping>> as GRPT_1 {', "GRPT_1"),
    ('rectangle "<$archimate_capability{scale=1.2}> Sprited" <<capability>> as CAP_d', "CAP_d"),
    ('rectangle "Stereotyped after" as CAP_e <<Note>>', "CAP_e"),
]

_UNTOUCHABLE = [
    "@startuml resource-investment-map",
    "skinparam linetype ortho",
    "' Connections",
    "RES_JnWnY1 -up-> CAP_pLMHKe",
    'Rel_Realization(REQ_kOU3al, OUT_620dTh, "")',
    "}",
    "@enduml",
]


def _body(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


class TestTheAliasSurvives:
    @pytest.mark.parametrize(("line", "alias"), _FORMS, ids=[alias for _line, alias in _FORMS])
    def test_a_colour_leaves_the_alias_declared(self, line: str, alias: str) -> None:
        restyled = restyled_declaration(line, fill="dc2626", border="48391C", ink="f5f5f5")

        assert [d.alias for d in declared_aliases(restyled)] == [alias]

    @pytest.mark.parametrize(("line", "alias"), _FORMS, ids=[alias for _line, alias in _FORMS])
    def test_an_appended_label_line_leaves_the_alias_declared(self, line: str, alias: str) -> None:
        restyled = restyled_declaration(line, label_lines=("investment_level: 4",))

        assert [d.alias for d in declared_aliases(restyled)] == [alias]

    @pytest.mark.parametrize(("line", "alias"), _FORMS, ids=[alias for _line, alias in _FORMS])
    def test_both_at_once_leave_the_alias_declared(self, line: str, alias: str) -> None:
        restyled = restyled_declaration(
            line, fill="dc2626", border="48391C", ink="f5f5f5", label_lines=("severity: major",)
        )

        assert [d.alias for d in declared_aliases(restyled)] == [alias]

    def test_a_whole_body_round_trips_with_every_form_present(self) -> None:
        """The property that matters: the same aliases, in the same order, before and after."""
        body = _body([*_UNTOUCHABLE[:3], *[line for line, _alias in _FORMS], *_UNTOUCHABLE[3:]])
        before = [(d.alias, d.opens_block) for d in declared_aliases(body)]

        restyled = _body([
            restyled_declaration(line, fill="fbbf24", border="48391C", ink="252327",
                                 label_lines=("investment_level: 3",))
            for line in body.splitlines()
        ])

        assert [(d.alias, d.opens_block) for d in declared_aliases(restyled)] == before


class TestWhatMustNotChange:
    @pytest.mark.parametrize("line", _UNTOUCHABLE)
    def test_a_line_that_declares_nothing_is_returned_unchanged(self, line: str) -> None:
        """Including the relation macro. `Rel_Realization(A, B, "")` names two aliases and declares
        neither — reading its first argument as a declaration once reported three duplicates in a
        diagram that draws each element exactly once."""
        assert restyled_declaration(line, fill="dc2626", label_lines=("x: 1",)) == line

    def test_a_line_opening_a_block_still_opens_it(self) -> None:
        """`opens_block` is the caller's separate question, and encoding it as "the line ends after the
        alias" is what made a coloured element neither leaf nor container."""
        line = 'rectangle "Grouping" <<StrategyGrouping>> as GRPT_1 {'

        restyled = restyled_declaration(line, fill="dc2626", label_lines=("count: 5",))

        assert declared_aliases(restyled)[0].opens_block is True

    def test_a_label_containing_the_word_as_is_not_split(self) -> None:
        line = 'rectangle "AI-Assisted Development as Dominant Production Mode" as DRV_q'

        restyled = restyled_declaration(line, label_lines=("owner: platform",))

        assert "AI-Assisted Development as Dominant Production Mode" in restyled
        assert [d.alias for d in declared_aliases(restyled)] == ["DRV_q"]

    def test_restyling_nothing_returns_the_line_it_was_given(self) -> None:
        """No colour and no label lines is not a request; it must not rewrite anything."""
        line = 'rectangle "Plain" <<capability>> as CAP_a #EFBD5D'

        assert restyled_declaration(line) == line


class TestWhatTheRestyleActuallyDoes:
    def test_a_colour_replaces_an_existing_one_rather_than_adding_a_second(self) -> None:
        line = 'rectangle "Already coloured" as CAP_b #EFBD5D'

        restyled = restyled_declaration(line, fill="dc2626", border="48391C", ink="f5f5f5")

        assert restyled.count("#") == 1
        assert "#back:dc2626;line:48391C;text:f5f5f5" in restyled
        assert "EFBD5D" not in restyled

    def test_a_compound_colour_is_replaced_whole(self) -> None:
        line = 'rectangle "Compound" as CAP_c #back:EFBD5D;line:48391C;text:252327'

        restyled = restyled_declaration(line, fill="dc2626", border="111111", ink="ffffff")

        assert restyled.count("#") == 1
        assert "#back:dc2626;line:111111;text:ffffff" in restyled

    def test_label_lines_are_appended_inside_the_quoted_label(self) -> None:
        line = 'rectangle "Name" <<capability>> as CAP_a'

        restyled = restyled_declaration(line, label_lines=("investment_level: 4", "severity: major"))

        assert '"Name\\n' in restyled
        assert "investment_level: 4" in restyled
        assert "severity: major" in restyled

    def test_a_second_restyle_replaces_the_first_rather_than_stacking(self) -> None:
        """A reader changing their choice must not accumulate lines from every choice they made."""
        line = 'rectangle "Name" <<capability>> as CAP_a'

        once = restyled_declaration(line, fill="dc2626", label_lines=("investment_level: 4",))
        twice = restyled_declaration(once, fill="fbbf24", label_lines=("severity: major",))

        assert twice.count("investment_level") == 0
        assert twice.count("severity: major") == 1
        assert [d.alias for d in declared_aliases(twice)] == ["CAP_a"]

    def test_an_unquoted_declaration_is_left_alone_rather_than_guessed_at(self) -> None:
        """`rectangle CAP_a` has no label to append to. Refusing is better than inventing one: a
        renderer that quoted it would change what the element is called."""
        line = "rectangle CAP_a"

        assert restyled_declaration(line, label_lines=("x: 1",)) == line
