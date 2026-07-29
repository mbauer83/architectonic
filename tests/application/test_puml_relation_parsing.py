"""Every form a PUML body can state a relation in — read by one parser.

The parser used to recognise only the macro call and the stereotype-labelled arrow. The renderer
emits neither: it writes bare arrows and leaves the `!define Rel_*` header lines uncalled. So a
generated diagram read as declaring nothing, its binding set could never be recovered from its own
body, and a relation drawn but unbound was deleted by the next refresh. The contract test at the
bottom is the one whose absence allowed the two halves to drift apart.
"""

from __future__ import annotations

from src.application.puml_relation_parsing import DeclaredRelation, declared_relations

_STEREOTYPES = {
    "triggering": "archimate-triggering",
    "influence": "archimate-influence",
    "serving": "archimate-serving",
}


def _pairs(body: str) -> list[tuple[str, str, str | None]]:
    return [
        (relation.source_alias, relation.target_alias, relation.connection_type)
        for relation in declared_relations(body, _STEREOTYPES)
    ]


class TestTheThreeFormsAreAllRead:
    def test_a_macro_call_states_its_type(self) -> None:
        assert _pairs("Rel_Triggering(FNC_a, FNC_b, label)") == [("FNC_a", "FNC_b", "archimate-triggering")]

    def test_a_directional_macro_suffix_is_not_part_of_the_type(self) -> None:
        assert _pairs("Rel_Triggering_Up(FNC_a, FNC_b, label)") == [("FNC_a", "FNC_b", "archimate-triggering")]

    def test_a_stereotype_label_states_its_type(self) -> None:
        assert _pairs("FNC_a --> FNC_b : <<serving>>") == [("FNC_a", "FNC_b", "archimate-serving")]

    def test_a_bare_arrow_is_read_with_no_type(self) -> None:
        """The form the renderer actually emits. It names endpoints; the glyph cannot name a type,
        because `..>` is the declared arrow of both access and influence."""
        assert _pairs("ASS_x ..> GOL_y") == [("ASS_x", "GOL_y", None)]
        assert _pairs("FNC_a --> FNC_b") == [("FNC_a", "FNC_b", None)]
        assert _pairs("PRC_p .up.|> SRV_s") == [("PRC_p", "SRV_s", None)]

    def test_a_bare_arrow_carrying_a_plain_label_is_still_read(self) -> None:
        assert _pairs("ASS_x .down.> GOL_y : <color:#b91c1c><b>-</b></color>") == [("ASS_x", "GOL_y", None)]

    def test_the_drawn_glyph_is_carried_for_disambiguation(self) -> None:
        assert declared_relations("ASS_x ..> GOL_y", _STEREOTYPES) == [
            DeclaredRelation("ASS_x", "GOL_y", None, "..>")
        ]


class TestWhatIsNotARelation:
    def test_a_hidden_layout_link_is_not_a_relation(self) -> None:
        """A hidden link positions elements and asserts nothing about the model. Reading one as a
        relation would bind a connection the diagram never claimed."""
        assert _pairs("FNC_a -[hidden]down- FNC_b") == []
        assert _pairs("FNC_a -[hidden]right- FNC_b") == []

    def test_the_define_header_lines_are_not_relations(self) -> None:
        """`!define Rel_Triggering(from, to, label) from --> to` contains both a macro name and an
        arrow. Anchoring per line keeps it out — nothing declares a relation between `from` and
        `to`."""
        body = (
            "!define Rel_Triggering(from, to, label) from --> to\n"
            "!define Rel_Influence(from, to, label) from ..> to\n"
        )
        assert _pairs(body) == []

    def test_declarations_and_skinparams_are_not_relations(self) -> None:
        body = (
            'rectangle "<$sprite> Name\\n«Business Process»" <<process>> as PRC_x {\n'
            "skinparam rectangle<<CommonGrouping>> {\n"
            "  BackgroundColor #EDE8E1\n"
            "}\n"
            "title Some Diagram\n"
        )
        assert _pairs(body) == []

    def test_an_unknown_stereotype_is_dropped_rather_than_guessed(self) -> None:
        assert _pairs("FNC_a --> FNC_b : <<notatype>>") == []

    def test_a_stereotyped_arrow_is_not_also_counted_as_untyped(self) -> None:
        """Reading it twice would discard the type the body went to the trouble of stating."""
        assert _pairs("FNC_a --> FNC_b : <<triggering>>") == [("FNC_a", "FNC_b", "archimate-triggering")]


class TestTheGeneratorAndTheParserAgree:
    """The contract that was never tested, and so was never kept.

    A body the renderer produced must read back as declaring exactly the relations it drew. Held
    against a verbatim excerpt of generated output — header defines, sprites, groupings, hidden
    layout chains and bare arrows — because that combination is what the parser has to survive.
    """

    _GENERATED = """@startuml promote-artifacts
hide stereotype
skinparam linetype ortho
!define Rel_Triggering(from, to, label) from --> to
!define Rel_Realization(from, to, label) from ..|> to
!define Rel_Influence(from, to, label) from ..> to
skinparam rectangle<<CommonGrouping>> {
  BackgroundColor #EDE8E1
}

top to bottom direction

title Promote Artifacts

rectangle "Processes" <<CommonGrouping>> {
  rectangle "<$archimate_process{scale=1.2}> Promote Artifacts" <<process>> as PRC_0Rz5Ex {
    rectangle "<$archimate_function{scale=1.2}> Select Artifacts" <<function>> as FNC_Z2rrfP
    rectangle "<$archimate_function{scale=1.2}> Detect Conflicts" <<function>> as FNC_ndMgDn
    FNC_Z2rrfP -[hidden]down- FNC_ndMgDn
  }
}
SRV_Uv9Wx9 -[hidden]down- PRC_0Rz5Ex

' Connections
PRC_0Rz5Ex .up.|> SRV_Uv9Wx9
FNC_Z2rrfP --> FNC_ndMgDn
FNC_ndMgDn --> EVT_Dm0CyE

@enduml
"""

    def test_every_arrow_the_generator_drew_is_recovered(self) -> None:
        assert [p for p in _pairs(self._GENERATED) if p[0] != "PRC_0Rz5Ex" or p[1] == "SRV_Uv9Wx9"] == [
            ("PRC_0Rz5Ex", "SRV_Uv9Wx9", None),
            ("FNC_Z2rrfP", "FNC_ndMgDn", None),
            ("FNC_ndMgDn", "EVT_Dm0CyE", None),
        ]

    def test_the_containment_the_generator_nested_is_recovered(self) -> None:
        """The process nests the functions it orchestrates, which is how composition and aggregation
        are drawn. Reading only arrows lost that: the refreshed diagram had no structural edge left
        to nest by, so it flattened into boxes grouped by element type."""
        assert ("PRC_0Rz5Ex", "FNC_Z2rrfP", None) in _pairs(self._GENERATED)
        assert ("PRC_0Rz5Ex", "FNC_ndMgDn", None) in _pairs(self._GENERATED)

    def test_no_layout_chain_or_header_line_is_mistaken_for_one(self) -> None:
        """The count is the whole point: three arrows and two nestings, five relations. Six would
        mean a hidden chain, a `!define`, or the grouping rectangle had become a model relation."""
        assert len(declared_relations(self._GENERATED, _STEREOTYPES)) == 5

    def test_a_grouping_rectangle_is_not_a_parent(self) -> None:
        """`rectangle "Processes" <<CommonGrouping>> {` names a box, not an element. Treating it as a
        parent would bind a containment relation the model never stated."""
        assert not [p for p in _pairs(self._GENERATED) if p[0] in {"Processes", ""}]


class TestThereIsExactlyOneParser:
    """Three blind copies of this parsing once existed and drifted into failing open — the
    verifier rule, the reference inferencer and the reconcile each saw a generated body as
    declaring nothing. Every reader must go through `declared_relations`; a module that grows
    its own relation regex back is re-planting the drift this file exists to prevent."""

    _FORMER_COPIES = (
        "src.application.verification._verifier_rules_puml_relations",
        "src.infrastructure.write.artifact_write.diagram_references",
        "src.infrastructure.write.artifact_write._sync_helpers",
    )

    def test_no_former_copy_carries_its_own_relation_regex(self) -> None:
        import importlib
        import inspect

        for module_name in self._FORMER_COPIES:
            source = inspect.getsource(importlib.import_module(module_name))
            assert "declared_relations" in source, f"{module_name} no longer reads the shared parser"
            assert "Rel_(?P" not in source, f"{module_name} regrew a private relation-macro regex"
            assert "_REL_LINE_RE" not in source, f"{module_name} regrew a private relation-arrow regex"
