"""Relabelling a declaration renames its element and changes nothing else about it.

The second write into a declaration's quoted label, after the reading lens's appended lines, and
held to the same round trip: relabel, read back with `declared_aliases`, and the same aliases are
declared in the same order with `opens_block` unchanged. Its reading twin, `label_declared_on`, is
what an editor shows for an instance whose body calls an element something its record does not — so
the pair is asserted together: what one writes, the other reads back.

**Stated over what the syntax permits.** A label may carry quotes, newlines, the word `as`, a
colour-looking `#` or guillemets; a declaration may carry a sprite before the label, a
specialization line and a reading lens's block after it, a colour after the alias, and a block
opener. Every form the owner's docstring names is here, plus the lines that must not be touched.
"""

from __future__ import annotations

import pytest

from src.application.puml_alias_declarations import (
    declared_aliases,
    label_declared_on,
    relabelled_declaration,
    restyled_declaration,
)

_FORMS = [
    ('rectangle "Plain" <<capability>> as CAP_a', "CAP_a", "Plain"),
    ('rectangle "Already coloured" <<capability>> as CAP_b #EFBD5D', "CAP_b", "Already coloured"),
    ('rectangle "Compound colour" as CAP_c #back:EFBD5D;line:48391C;text:252327', "CAP_c", "Compound colour"),
    ('rectangle "AI-Assisted Development as Dominant Production Mode" as DRV_q', "DRV_q",
     "AI-Assisted Development as Dominant Production Mode"),
    ('rectangle "Hyphenated" as CAP-with-hyphen', "CAP-with-hyphen", "Hyphenated"),
    ('rectangle "Opens a block" <<StrategyGrouping>> as GRPT_1 {', "GRPT_1", "Opens a block"),
    ('rectangle "<$archimate_capability{scale=1.2}> Sprited" <<capability>> as CAP_d', "CAP_d", "Sprited"),
    ('rectangle "Stereotyped after" as CAP_e <<Note>>', "CAP_e", "Stereotyped after"),
    ('  rectangle "<$archimate_outcome{scale=1.2}> Validated Before Implementation" <<outcome>> as OUT_a5mNob',
     "OUT_a5mNob", "Validated Before Implementation"),
    ('rectangle "Specialised\\n«Business Collaboration»" <<collaboration>> as COL_1', "COL_1", "Specialised"),
    ('rectangle "Read\\n<size:10>investment_level: 4</size>" <<capability>> as CAP_f', "CAP_f", "Read"),
]

_UNTOUCHABLE = [
    "@startuml resource-investment-map",
    "skinparam linetype ortho",
    "' Connections",
    "RES_JnWnY1 -up-> CAP_pLMHKe",
    'Rel_Realization(REQ_kOU3al, OUT_620dTh, "")',
    "rectangle Bare as CAP_unquoted",
    "}",
    "@enduml",
]

_LABELS = [
    "Short",
    'He said "as GOL_ZZ"',
    "Cost #red herring",
    "A <<not a stereotype>> B",
    "Two\nlines\tand   spacing",
    "Guillemets «inside» the name",
]


class TestReadingTheLabel:
    @pytest.mark.parametrize(("line", "_alias", "label"), _FORMS, ids=[alias for _l, alias, _n in _FORMS])
    def test_the_label_is_the_name_without_sprite_or_appended_lines(self, line: str, _alias: str, label: str) -> None:
        assert label_declared_on(line) == label

    @pytest.mark.parametrize("line", _UNTOUCHABLE)
    def test_a_line_that_declares_no_quoted_label_reports_none(self, line: str) -> None:
        assert label_declared_on(line) is None

    def test_a_junction_is_declared_with_an_empty_label(self) -> None:
        assert label_declared_on('circle " " as JNA_x #252327') == ""


class TestTheRoundTrip:
    @pytest.mark.parametrize("label", _LABELS)
    @pytest.mark.parametrize(("line", "alias", "_label"), _FORMS, ids=[alias for _l, alias, _n in _FORMS])
    def test_the_alias_and_its_block_survive_and_the_label_reads_back(
        self, line: str, alias: str, _label: str, label: str,
    ) -> None:
        before = [(d.alias, d.opens_block) for d in declared_aliases(line)]

        relabelled = relabelled_declaration(line, label)

        assert [(d.alias, d.opens_block) for d in declared_aliases(relabelled)] == before == [(alias, before[0][1])]
        # One line in, one line out: a newline inside the quotes would have ended the declaration.
        assert "\n" not in relabelled
        assert label_declared_on(relabelled) == " ".join(label.split()).replace('"', "'")

    @pytest.mark.parametrize("line", _UNTOUCHABLE)
    def test_a_line_that_declares_nothing_quoted_is_returned_unchanged(self, line: str) -> None:
        assert relabelled_declaration(line, "Anything") == line

    def test_the_sprite_and_the_appended_lines_are_kept(self) -> None:
        sprite, appended = "<$archimate_capability{scale=1.2}> ", "\\n«Spec»\\n<size:10>x: 1</size>"
        line = f'rectangle "{sprite}Old{appended}" <<capability>> as CAP_g'

        relabelled = relabelled_declaration(line, "New")

        assert relabelled == f'rectangle "{sprite}New{appended}" <<capability>> as CAP_g'

    def test_a_relabel_and_a_restyle_compose_in_either_order(self) -> None:
        line = 'rectangle "Old" <<capability>> as CAP_h'

        one = restyled_declaration(relabelled_declaration(line, "New"), fill="dc2626", label_lines=("k: 1",))
        other = relabelled_declaration(restyled_declaration(line, fill="dc2626", label_lines=("k: 1",)), "New")

        assert one == other
        assert label_declared_on(one) == "New"
        assert [d.alias for d in declared_aliases(one)] == ["CAP_h"]
