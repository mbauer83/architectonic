"""A layout written into a diagram file is the layout read back out of it, for everything the block permits.

The pair under test is the real one: `format_diagram_puml` writes the frontmatter and
`parse_frontmatter` reads it, with `layout_as_written` and `read_layout` between the value and the
mapping. Stated over what the syntax *permits* — any instance id, grouping id, rule key or relation
key, sized or not, ported or not, with or without bends, a label, a stacking — not over what an
editor happens to emit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.modeling.diagram_file_format import format_diagram_puml
from src.domain.artifact_id import is_entity_id
from src.domain.diagrams.authored_groupings import GroupingRule, RuleKey
from src.domain.diagrams.drawn_relations import SOURCE_OCCURRENCE_KEY, TARGET_OCCURRENCE_KEY
from src.domain.diagrams.layout.layout_block import (
    LabelAnchor,
    Layout,
    MalformedLayout,
    Placed,
    Port,
    Route,
    Side,
    layout_as_written,
    read_layout,
)
from src.domain.diagrams.relation_key import drawn_relation_key
from src.domain.repository.frontmatter import parse_frontmatter

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_entity_ids = st.builds(
    lambda prefix, epoch, random: f"{prefix}@{epoch}.{random}",
    st.sampled_from(["APP", "BOB", "PRC", "FNC", "JCT"]),
    st.integers(1_000_000_000, 1_999_999_999),
    st.text(_LETTERS, min_size=6, max_size=7),
)
_occurrence_ids = st.text(_LETTERS + "-_", min_size=1, max_size=12).map(lambda text: f"occ-{text}")
_instances = st.one_of(_entity_ids, _occurrence_ids)
_grouping_ids = st.text(_LETTERS, min_size=4, max_size=12).map(lambda letters: f"g-{letters}")
_names = st.from_regex(r"[a-z0-9][a-z0-9_-]{0,12}", fullmatch=True)
_rules = st.builds(GroupingRule, st.sampled_from(["domain", "type"]), _names)
_rule_keys = st.builds(
    RuleKey, st.lists(_rules, min_size=1, max_size=3).map(tuple), st.one_of(st.just(1), st.integers(2, 9))
).map(lambda key: key.text)
_whole = st.integers(-5_000, 50_000)
_size = st.integers(1, 5_000)
_fractions = st.one_of(st.sampled_from([0.0, 1.0, 0.5]), st.floats(0, 1, allow_nan=False).map(lambda f: round(f, 3)))
_placed = st.one_of(st.builds(Placed, _whole, _whole), st.builds(Placed, _whole, _whole, _size, _size))
_ports = st.builds(Port, st.sampled_from(list(Side)), _fractions)
_routes = st.builds(
    Route,
    source=st.none() | _ports,
    target=st.none() | _ports,
    via=st.lists(st.tuples(_whole, _whole), max_size=4).map(tuple),
    label=st.none() | st.builds(LabelAnchor, _fractions, _whole, _whole),
)


@dataclass(frozen=True)
class _Drawn:
    """One relation a diagram draws: a connection, and the occurrence at either end where one is named."""

    source: str
    target: str
    kind: str
    source_occurrence: str | None
    target_occurrence: str | None

    @property
    def connection(self) -> str:
        return f"{self.source}---{self.target}@@archimate-{self.kind}"

    @property
    def key(self) -> str:
        return drawn_relation_key(
            self.connection, source=self.source, target=self.target,
            source_instance=self.source_occurrence or self.source,
            target_instance=self.target_occurrence or self.target,
        ).text


_drawn = st.builds(
    _Drawn, _entity_ids, _entity_ids, st.sampled_from(["serving", "flow", "composition"]),
    st.none() | _occurrence_ids, st.none() | _occurrence_ids,
)


@dataclass(frozen=True)
class _Stated:
    """A layout, and the relations it routes — which the diagram holding it has to draw."""

    layout: Layout
    drawn: tuple[_Drawn, ...]


@st.composite
def _stated_layouts(draw: st.DrawFn) -> _Stated:
    routed = draw(st.lists(st.tuples(_drawn, _routes), max_size=3, unique_by=lambda pair: pair[0].key))
    layout = Layout(
        grid=draw(st.none() | st.integers(1, 100)),
        elements=draw(st.dictionaries(_instances, _placed, max_size=4)),
        boxes=draw(st.dictionaries(st.one_of(_grouping_ids, _rule_keys), _placed, max_size=3)),
        relations={relation.key: route for relation, route in routed},
        z=draw(st.dictionaries(st.one_of(_instances, _grouping_ids, _rule_keys), st.integers(-9, 9), max_size=4)),
    )
    return _Stated(layout, tuple(relation for relation, _route in routed))


def _through_a_diagram_file(stated: _Stated) -> object:
    """Write the layout into a diagram that holds everything it names, and read the block back."""
    layout = stated.layout
    named = [*layout.elements, *layout.z]
    occurrences = sorted(
        {key for key in named if key.startswith("occ-")}
        | {occ for relation in stated.drawn for occ in (relation.source_occurrence, relation.target_occurrence) if occ}
    )
    backing = "APP@1000000001.backing"
    written = format_diagram_puml(
        artifact_id="ARC@1700000000.AbCdEf.a-view", diagram_type="archimate-application", name="A View",
        version="0.1.0", status="draft", last_updated="2026-11-20T00:00:00Z",
        puml_body="@startuml a-view\ntitle A View\n@enduml\n",
        entity_ids_used=[backing, *(key for key in named if is_entity_id(key))],
        connection_ids_used=[relation.connection for relation in stated.drawn],
        diagram_entities={"occurrence": [{"id": occ, "backing_entity_id": backing} for occ in occurrences]},
        diagram_connections=[
            {
                "artifact_id": relation.connection,
                **({SOURCE_OCCURRENCE_KEY: relation.source_occurrence} if relation.source_occurrence else {}),
                **({TARGET_OCCURRENCE_KEY: relation.target_occurrence} if relation.target_occurrence else {}),
            }
            for relation in stated.drawn
        ],
        authored_groupings=[
            {"id": key, "label": key} for key in (*layout.boxes, *layout.z) if key.startswith("g-")
        ],
        layout=layout_as_written(layout),
    )
    return parse_frontmatter(written).get("layout")


@settings(max_examples=150, deadline=None)
@given(_stated_layouts())
def test_a_layout_survives_the_file_it_is_written_into(stated: _Stated) -> None:
    stored = _through_a_diagram_file(stated)

    if stated.layout == Layout():
        assert stored is None, "a layout that states nothing writes no block"
        return
    assert read_layout(stored) == stated.layout


@settings(max_examples=100, deadline=None)
@given(_stated_layouts())
def test_what_is_read_is_written_back_identically(stated: _Stated) -> None:
    """The other direction: a block in canonical spelling is a fixed point of read-then-write."""
    written = layout_as_written(stated.layout)

    assert layout_as_written(read_layout(written)) == written


def test_an_entity_is_keyed_by_its_stable_id_however_it_was_spelled() -> None:
    long_form = "APP@1712870400.xVrBYD.plantuml-engine"

    layout = read_layout({"elements": {long_form: {"x": 1, "y": 2}}, "z": {long_form: 3}})

    assert list(layout.elements) == ["APP@1712870400.xVrBYD"]
    assert list(layout.z) == ["APP@1712870400.xVrBYD"]


@pytest.mark.parametrize(
    ("block", "says"),
    [
        ([], "expected a mapping"),
        ({"colour": "red"}, "states colour"),
        ({"grid": 0}, "at least 1"),
        ({"grid": 2.5}, "whole number"),
        ({"elements": {"APP@1.abcdef": {"x": 1}}}, "both x and y"),
        ({"elements": {"APP@1.abcdef": {"x": 1, "y": 2, "w": 10}}}, "both or neither"),
        ({"elements": {"APP@1.abcdef": {"x": 1, "y": 2, "w": 0, "h": 5}}}, "not positive"),
        ({"elements": {"APP@1.abcdef": {"x": 1.5, "y": 2}}}, "whole number"),
        ({"elements": {"APP@1.abcdef": {"x": True, "y": 2}}}, "whole number"),
        ({"elements": {"APP@1.abcdef": {"x": 1, "y": 2, "angle": 3}}}, "states angle"),
        ({"elements": {"APP@1.abcdef": {"x": 1, "y": 2}, "APP@1.abcdef.slug": {"x": 3, "y": 4}}}, "twice"),
        ({"boxes": {"rule:colour=red": {"x": 1, "y": 2}}}, "not a rule key"),
        ({"boxes": {"rule:domain=business#1": {"x": 1, "y": 2}}}, "numbered from '#2'"),
        ({"relations": {"APP_a:APP_b": {}}}, "arch-repair upgrade"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving@only-one-end>": {}}}, "not a drawn-relation key"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving": {"from": {"side": "north"}}}}, "one of top, right"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving": {"from": {"side": "top", "at": 1.5}}}}, "fraction"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving": {"via": [[1, 2, 3]]}}}, "a bend is a point"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving": {"via": [[1.5, 2]]}}}, "whole number"),
        ({"relations": {"A@1.aaaaaa---B@2.bbbbbb@@serving": {"label": {"at": -0.1}}}}, "fraction"),
        ({"z": {"APP@1.abcdef": "front"}}, "whole number"),
    ],
)
def test_a_malformed_block_is_refused_with_a_sentence(block: object, says: str) -> None:
    with pytest.raises(MalformedLayout) as refusal:
        read_layout(block)

    assert says in str(refusal.value)
    assert str(refusal.value).rstrip().endswith("."), "a refusal is a sentence"
