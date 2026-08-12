"""One reading of "this line declares an alias", and the shapes the five it replaced disagreed on.

Each case here is a shape that at least one of the five got wrong, and the last group is the round
trip that would have caught the defect on the day it arrived: **what the renderer writes, the writer
must be able to read back**. Nothing asserted that, so a declaration carrying a trailing colour was
invisible to the reader that derives `entity-ids-used` while the verifier — resolving drawn aliases a
different way — saw it perfectly well, and refused the diagram (E315) for omitting an entity the
writer had dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.parsing import extract_declared_puml_aliases
from src.application.puml_alias_declarations import (
    AliasDeclaration,
    alias_declared_on,
    declared_aliases,
    macro_alias_declared_on,
)
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.rendering.archimate_entity_declarations import (
    entity_declaration,
    entity_nest_declaration,
)


class TestWhatDeclaresAnAlias:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            # The shape the end-anchored readings lost, and the one the report arrived as: a junction
            # is drawn as a coloured circle.
            ('circle " " as JNA_crPItzE #252327', AliasDeclaration("JNA_crPItzE", False)),
            # Not junction-specific — any coloured declaration was lost the same way.
            ('rectangle "Explore" <<function>> as FNC_x #E6F3FF', AliasDeclaration("FNC_x", False)),
            ('rectangle "Explore" <<function>> as FNC_x #E6F3FF {', AliasDeclaration("FNC_x", True)),
            ('rectangle "Explore" <<function>> as FNC_x', AliasDeclaration("FNC_x", False)),
            ('rectangle "Explore" <<function>> as FNC_x {', AliasDeclaration("FNC_x", True)),
            # A hyphen is part of an alias; two of the five spelled it `\\w+` and truncated one.
            ('rectangle "X" as some-alias', AliasDeclaration("some-alias", False)),
            # A sprite label carries braces mid-line and opens no block.
            (
                'rectangle "<$archimate_function{scale=1.2}> Explore" <<function>> as FNC_x',
                AliasDeclaration("FNC_x", False),
            ),
        ],
    )
    def test_a_declaration_is_read_whatever_follows_the_alias(
        self, line: str, expected: AliasDeclaration
    ) -> None:
        assert alias_declared_on(line) == expected

    def test_prose_inside_a_label_declares_nothing(self) -> None:
        """One of the five stripped quotes before looking; the other four read `Dominant` as an alias."""
        line = 'rectangle "AI-Assisted Development as Dominant Production Mode" <<goal>> as GOL_y'

        assert alias_declared_on(line) == AliasDeclaration("GOL_y", False)

    @pytest.mark.parametrize(
        "line",
        [
            "' rectangle \"Commented out\" as NOPE",
            "FNC_a --> FNC_b",
            "@startuml something",
            "",
            "   ",
            "}",
        ],
    )
    def test_a_line_that_declares_nothing_reads_as_nothing(self, line: str) -> None:
        assert alias_declared_on(line) is None

    def test_the_body_reading_keeps_declaration_order(self) -> None:
        body = 'rectangle "A" as A_1 {\ncircle " " as J_1 #252327\nrectangle "B" as B_1\n}'

        assert declared_aliases(body) == [
            AliasDeclaration("A_1", True),
            AliasDeclaration("J_1", False),
            AliasDeclaration("B_1", False),
        ]

    def test_a_macro_call_declares_its_first_argument(self) -> None:
        assert macro_alias_declared_on('Person(user, "User", "…")') == "user"
        assert macro_alias_declared_on("FNC_a --> FNC_b") is None


def _entity(artifact_type: str, alias: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"XXX@1.a.{alias.lower()}",
        artifact_type=artifact_type,
        name="Some Element",
        version="0.1.0",
        status="draft",
        domain="business",
        subdomain=artifact_type,
        path=Path(f"/tmp/{alias}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="Some Element",
        display_alias=alias,
        specializations=(),
    )


def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _archimate_entity_types() -> list[str]:
    """Every entity type the ArchiMate declaration renderer can be asked to draw."""
    return sorted(str(name) for name in _registry().all_entity_types())


#: Decorations PlantUML permits after an alias. Each one is written by something real: the renderer
#: appends `color_suffix` for a specialization that declares a notation colour, and a hand-authored
#: body appends one to make a junction's circle visible — which is exactly how the defect arrived.
#:
#: Parameterised rather than left to whatever the renderer emits *today*: the shipped specialization
#: catalogue currently declares no colours, so a round trip over the renderer's output alone passes
#: against the broken reading. Measured — that is not a guess: the first version of this file gated
#: nothing for precisely that reason.
_DECORATIONS = ("", " #E6F3FF", " #252327", " <<Note>>")


class TestWhatTheRendererWritesTheWriterCanRead:
    """The gate that was missing, and the reason it has to be stated over decorations too.

    Over the whole catalogue rather than over junctions, because the next type drawn with something
    after its alias must not have to be found in a bug report either.
    """

    @pytest.mark.parametrize("decoration", _DECORATIONS)
    @pytest.mark.parametrize("artifact_type", _archimate_entity_types())
    def test_a_decorated_declaration_still_names_its_entity(
        self, artifact_type: str, decoration: str
    ) -> None:
        """The whole defect in one assertion: the writer must read what a body may legally contain."""
        alias = "ALS_x0"
        line = entity_declaration(
            _entity(artifact_type, alias), alias, _registry(), frozenset({"and-junction", "or-junction"})
        ) + decoration

        assert extract_declared_puml_aliases(line) == {alias}, line

    @pytest.mark.parametrize("artifact_type", _archimate_entity_types())
    def test_a_rendered_declaration_round_trips_into_the_alias_it_declares(
        self, artifact_type: str
    ) -> None:
        alias = "ALS_x1"
        junction_types = frozenset({"and-junction", "or-junction"})
        line = entity_declaration(
            _entity(artifact_type, alias), alias, _registry(), junction_types
        )

        assert extract_declared_puml_aliases(line) == {alias}, line

    @pytest.mark.parametrize("artifact_type", _archimate_entity_types())
    def test_a_rendered_container_declaration_round_trips_and_reads_as_a_container(
        self, artifact_type: str
    ) -> None:
        alias = "ALS_x2"
        junction_types = frozenset({"and-junction", "or-junction"})
        line = entity_nest_declaration(
            _entity(artifact_type, alias), alias, _registry(), junction_types
        )
        declaration = alias_declared_on(line)

        assert declaration is not None, line
        assert declaration.alias == alias
        # A junction is a circle and never nests, so only the nesting forms open a block.
        assert declaration.opens_block == line.rstrip().endswith("{"), line
