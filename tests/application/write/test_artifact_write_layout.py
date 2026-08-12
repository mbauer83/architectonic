"""Tests for artifact_write_layout.py: pure PlantUML layout optimization.

Covers: _parse_groupings, _detect_direction, _select_direction and ensure_puml_layout.
Inserting a direction into an arrow token moved to its owner — see
tests/application/test_puml_arrow_tokens.py.
"""

from __future__ import annotations

from src.application.modeling.artifact_write_layout import (
    _detect_direction,
    _parse_groupings,
    _select_direction,
    ensure_puml_layout,
)

_SIMPLE_PUML = """\
@startuml
rectangle "Layer A" <<Application>> as la {
  component "Comp A" as compA
  component "Comp B" as compB
}
rectangle "Layer B" <<Technology>> as lb {
  component "Comp C" as compC
}
compA --> compC : uses
@enduml
"""

_SINGLE_GROUP_MANY_ELEMENTS = """\
@startuml
rectangle "Layer" <<Application>> as l {
  component "A" as a
  component "B" as b
  component "C" as c
  component "D" as d
  component "E" as e
  component "F" as f
}
@enduml
"""


class TestParseGroupings:
    def test_parses_two_groups(self) -> None:
        groups = _parse_groupings(_SIMPLE_PUML)
        assert len(groups) == 2
        assert groups[0].label == "Layer A"
        assert groups[1].label == "Layer B"

    def test_captures_aliases_within_group(self) -> None:
        groups = _parse_groupings(_SIMPLE_PUML)
        assert "compA" in groups[0].aliases
        assert "compB" in groups[0].aliases

    def test_empty_puml_returns_empty(self) -> None:
        groups = _parse_groupings("@startuml\n@enduml\n")
        assert groups == []

    def test_skips_comment_lines(self) -> None:
        puml = "@startuml\n' comment\nrectangle \"A\" <<X>> as a {\n  component \"X\" as x\n}\n@enduml\n"
        groups = _parse_groupings(puml)
        assert len(groups) == 1

    def test_group_index_increments(self) -> None:
        groups = _parse_groupings(_SIMPLE_PUML)
        assert groups[0].index == 0
        assert groups[1].index == 1

    def test_no_alias_if_brace_at_end(self) -> None:
        puml = (
            "@startuml\nrectangle \"A\" <<X>> as a {\n"
            "  rectangle \"Nested\" as n {\n    component \"X\" as x\n  }\n}\n@enduml\n"
        )
        groups = _parse_groupings(puml)
        assert groups is not None


class TestDetectDirection:
    def test_detects_top_to_bottom(self) -> None:
        puml = "top to bottom direction\n"
        assert _detect_direction(puml) == "top to bottom"

    def test_detects_left_to_right(self) -> None:
        puml = "left to right direction\n"
        assert _detect_direction(puml) == "left to right"

    def test_returns_none_when_absent(self) -> None:
        assert _detect_direction("@startuml\n@enduml\n") is None


class TestSelectDirection:
    def test_multiple_groups_selects_top_to_bottom(self) -> None:
        from src.application.modeling.artifact_write_layout import _GroupInfo

        groups = [_GroupInfo(label="A", index=0), _GroupInfo(label="B", index=1)]
        assert _select_direction(groups) == "top to bottom"

    def test_single_group_many_elements_selects_left_to_right(self) -> None:
        from src.application.modeling.artifact_write_layout import _GroupInfo

        group = _GroupInfo(label="A", index=0)
        group.aliases = ["a", "b", "c", "d", "e", "f"]
        assert _select_direction([group]) == "left to right"

    def test_single_group_few_elements_selects_top_to_bottom(self) -> None:
        from src.application.modeling.artifact_write_layout import _GroupInfo

        group = _GroupInfo(label="A", index=0)
        group.aliases = ["a", "b"]
        assert _select_direction([group]) == "top to bottom"

    def test_empty_groups_selects_top_to_bottom(self) -> None:
        assert _select_direction([]) == "top to bottom"


class TestOptimizePumlLayout:
    def test_noop_when_no_groups(self) -> None:
        puml = "@startuml\nA --> B\n@enduml\n"
        assert ensure_puml_layout(puml) == puml

    def test_noop_when_hidden_already_present(self) -> None:
        puml = "@startuml\nA -[hidden]- B\n@enduml\n"
        assert ensure_puml_layout(puml) == puml

    def test_noop_when_all_groups_have_fewer_than_2_aliases(self) -> None:
        puml = "@startuml\nrectangle \"G\" <<X>> as g {\n  component \"A\" as a\n}\na --> a\n@enduml\n"
        result = ensure_puml_layout(puml)
        assert "[hidden]" not in result

    def test_inserts_hidden_links_for_spreadable_group(self) -> None:
        result = ensure_puml_layout(_SIMPLE_PUML)
        assert "[hidden]" in result

    def test_inserts_direction_directive(self) -> None:
        result = ensure_puml_layout(_SIMPLE_PUML)
        assert "direction" in result

    def test_respects_existing_direction(self) -> None:
        puml = "left to right direction\n" + _SIMPLE_PUML
        result = ensure_puml_layout(puml)
        assert "left to right" in result

    def test_single_group_many_elements_uses_left_to_right(self) -> None:
        result = ensure_puml_layout(_SINGLE_GROUP_MANY_ELEMENTS)
        assert "left to right" in result
