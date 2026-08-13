"""A body's inlined copy of a generated declaration answers to the ontology, not to its author.

The generated ArchiMate includes have two storage forms: a body may keep the `!include` marker and
have it expanded at render time, or carry the expansion itself so the `.puml` renders on its own.
E303 accepts either. The second form is a *copy*, and until this was written the copy was refreshed
only as a side effect of regenerating the whole body — so a change to the palette, to a glyph or to
a relationship's line style reached a diagram only if something unrelated happened to rewrite it.

Nine of this repository's ArchiMate diagrams were therefore still drawing the colours they were
authored with and the pre-`-[dotted]-` access arrow, two of them not even hand-laid-out — their
content simply had not changed. The corner shapes, the whole point of the change that exposed this,
appeared on some motivation elements and not others for the same reason.

`stale_static_includes` gates the include files against the ontology. These gate every copy of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.rendering._archimate_includes import (
    ArchimateDeclarations,
    inject_archimate_includes,
)

_STEREOTYPES = """\
' _archimate-stereotypes.puml — ArchiMate skinparam definitions
' Auto-generated — do not edit manually.

hide stereotype

skinparam roundcorner 4

skinparam rectangle<<Grouping>> {
  BackgroundColor #FFFFFF
  BorderColor #9E9E9E
}
skinparam rectangle<<goal>> {
  BackgroundColor #D1BADC
  BorderColor #3F3842
  DiagonalCorner 10
}
skinparam rectangle<<business_process>> {
  BackgroundColor #EDD779
  BorderColor #474024
  RoundCorner 14
}
"""

_GLYPHS = """\
' _archimate-glyphs.puml — generated ArchiMate glyph sprites

hide stereotype

sprite $archimate_goal <svg><circle r="4"/></svg>
"""

_RELATIONS = """\
' _archimate-relations.puml — generated ArchiMate relationship macros (Rel_* syntax)

!define Rel_Access(from, to, label) from -[dotted]-> to
!define Rel_Realization_Up(from, to, label) from .up.|> to
"""


@pytest.fixture
def declarations() -> ArchimateDeclarations:
    return ArchimateDeclarations.from_includes(
        stereotypes=_STEREOTYPES, glyphs=_GLYPHS, relations=_RELATIONS
    )


class TestARestatementBringsAStaleCopyLevel:
    """Each case is a form one of the nine stale bodies was actually carrying."""

    def test_a_stale_colour_and_a_missing_corner_are_restated(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = (
            "@startuml\n"
            "skinparam rectangle<<goal>> {\n"
            "  BackgroundColor #EDD6F0\n"
            "  BorderColor #7B3F9A\n"
            "}\n"
            "@enduml\n"
        )

        assert declarations.restated_in(body) == (
            "@startuml\n"
            "skinparam rectangle<<goal>> {\n"
            "  BackgroundColor #D1BADC\n"
            "  BorderColor #3F3842\n"
            "  DiagonalCorner 10\n"
            "}\n"
            "@enduml\n"
        )

    def test_a_corner_that_should_no_longer_be_drawn_is_dropped(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """The block is replaced, not merged — otherwise a withdrawn corner would survive."""
        body = "skinparam rectangle<<Grouping>> {\n  BackgroundColor #FFF\n  RoundCorner 14\n}\n"

        assert "RoundCorner" not in declarations.restated_in(body)

    def test_a_stale_relationship_arrow_is_restated(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = "!define Rel_Access(from, to, label) from ..> to\n"

        assert declarations.restated_in(body) == (
            "!define Rel_Access(from, to, label) from -[dotted]-> to\n"
        )

    def test_a_macro_that_spells_its_parameters_differently_is_still_the_same_declaration(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = "!define Rel_Realization_Up(a, b, l) a ..|> b\n"

        assert declarations.restated_in(body) == (
            "!define Rel_Realization_Up(from, to, label) from .up.|> to\n"
        )

    def test_a_stale_glyph_is_restated(self, declarations: ArchimateDeclarations) -> None:
        body = 'sprite $archimate_goal <svg><circle r="9"/></svg>\n'

        assert declarations.restated_in(body) == 'sprite $archimate_goal <svg><circle r="4"/></svg>\n'


class TestARestatementIsNoOneElsesBusiness:
    """What a manual-layout diagram depends on: only the generated declarations move."""

    def test_layout_element_and_relation_lines_come_through_untouched(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = (
            "@startuml\n"
            "top to bottom direction\n"
            "skinparam nodesep 40\n"
            "title Why Assurance\n"
            'rectangle "Forces" <<Grouping>> {\n'
            '  rectangle "<$archimate_goal{scale=1.2}> A Goal" <<goal>> as GOL_x\n'
            "}\n"
            "GOL_x -[hidden]- GOL_y\n"
            'Rel_Access(GOL_x, GOL_y, "")\n'
            "@enduml\n"
        )

        restated = declarations.restated_in(body)

        for line in body.splitlines():
            if "skinparam rectangle" not in line:
                assert line in restated, line

    def test_a_declaration_the_ontology_does_not_make_is_left_alone(
        self, declarations: ArchimateDeclarations
    ) -> None:
        """Never removed and never invented: a body may declare something this ontology does not."""
        body = (
            "skinparam rectangle<<some_other_type>> {\n  BackgroundColor #123456\n}\n"
            "!define Rel_Invented(from, to, label) from --> to\n"
            "sprite $archimate_unknown <svg/>\n"
        )

        assert declarations.restated_in(body) == body

    def test_restating_twice_changes_nothing_the_second_time(
        self, declarations: ArchimateDeclarations
    ) -> None:
        body = "skinparam rectangle<<goal>> {\n  BackgroundColor #EDD6F0\n  BorderColor #7B3F9A\n}\n"

        once = declarations.restated_in(body)

        assert declarations.restated_in(once) == once


class TestTheTwoStorageFormsAnswerAlike:
    """The marker form was already current; this is the assertion that the other one is too."""

    def _repo(self, tmp_path: Path) -> Path:
        catalog = tmp_path / "diagram-catalog"
        catalog.mkdir(parents=True, exist_ok=True)
        (catalog / "_archimate-stereotypes.puml").write_text(_STEREOTYPES, encoding="utf-8")
        (catalog / "_archimate-glyphs.puml").write_text(_GLYPHS, encoding="utf-8")
        (catalog / "_archimate-relations.puml").write_text(_RELATIONS, encoding="utf-8")
        return tmp_path

    def test_an_expanded_marker_and_a_restated_copy_declare_the_same_goal(
        self, tmp_path: Path
    ) -> None:
        drawing = 'rectangle "<$archimate_goal> A Goal" <<goal>> as GOL_x\n'
        from_marker = inject_archimate_includes(
            "@startuml\n!include ../_archimate-stereotypes.puml\n" + drawing + "@enduml\n",
            self._repo(tmp_path),
        )
        from_copy = inject_archimate_includes(
            "@startuml\n"
            "skinparam rectangle<<goal>> {\n  BackgroundColor #EDD6F0\n  BorderColor #7B3F9A\n}\n"
            'sprite $archimate_goal <svg><circle r="9"/></svg>\n' + drawing + "@enduml\n",
            self._repo(tmp_path),
        )

        for expected in ("BackgroundColor #D1BADC", "DiagonalCorner 10", '<circle r="4"/>'):
            assert expected in from_marker, expected
            assert expected in from_copy, expected
        assert "#EDD6F0" not in from_copy


class TestABodyIsGivenAPreambleOrHasOneRestated:
    """`inject_includes` answers two different bodies and must not confuse them.

    It inserts the `!include` marker when a body has none, which is right for a body the renderer
    has just produced and wrong for one carrying the expansion: the marker then expands a *second*
    preamble beside the one already there. Measured while fixing the drift above — nine bodies came
    back with two of everything, the second copy still stale, and the picture drawn from whichever
    PlantUML honoured last.
    """

    def _repo(self, tmp_path: Path) -> Path:
        catalog = tmp_path / "diagram-catalog"
        catalog.mkdir(parents=True, exist_ok=True)
        (catalog / "_archimate-stereotypes.puml").write_text(_STEREOTYPES, encoding="utf-8")
        (catalog / "_archimate-glyphs.puml").write_text(_GLYPHS, encoding="utf-8")
        (catalog / "_archimate-relations.puml").write_text(_RELATIONS, encoding="utf-8")
        return tmp_path

    def _renderer(self):  # noqa: ANN202
        from src.infrastructure.diagram_type_registry import get_diagram_type  # noqa: PLC0415

        return get_diagram_type("archimate-motivation").renderer

    def test_an_already_expanded_body_gains_no_second_preamble(self, tmp_path: Path) -> None:
        body = (
            "@startuml\n"
            "skinparam rectangle<<goal>> {\n  BackgroundColor #EDD6F0\n  BorderColor #7B3F9A\n}\n"
            "!define Rel_Access(from, to, label) from ..> to\n"
            'rectangle "A Goal" <<goal>> as GOL_x\n'
            "@enduml\n"
        )

        result = self._renderer().inject_includes(body, self._repo(tmp_path))

        assert result.count("skinparam rectangle<<goal>>") == 1
        assert result.count("!define Rel_Access(") == 1
        assert "BackgroundColor #D1BADC" in result
        assert "from -[dotted]-> to" in result

    def test_a_body_with_no_preamble_is_still_given_one(self, tmp_path: Path) -> None:
        body = "@startuml\n" 'rectangle "A Goal" <<goal>> as GOL_x\n' "@enduml\n"

        result = self._renderer().inject_includes(body, self._repo(tmp_path))

        assert "skinparam rectangle<<goal>>" in result
        assert "DiagonalCorner 10" in result


class TestAnEditBringsAStoredBodyLevel:
    """The write path, end to end: the scenario the nine stale diagrams were in.

    The edit carries no body — a hand-laid-out diagram's body is kept verbatim, and an edit that
    only touches frontmatter never regenerated one. That branch is the sole route by which such a
    diagram hears about an ontology change, and it did not take it.
    """

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        (root / "model").mkdir(parents=True)
        catalog = root / "diagram-catalog"
        (catalog / "diagrams").mkdir(parents=True)
        (catalog / "_archimate-stereotypes.puml").write_text(_STEREOTYPES, encoding="utf-8")
        (catalog / "_archimate-glyphs.puml").write_text(_GLYPHS, encoding="utf-8")
        (catalog / "_archimate-relations.puml").write_text(_RELATIONS, encoding="utf-8")
        return root

    def _stale_body(self, artifact_id: str) -> str:
        return (
            f"@startuml {artifact_id}\n"
            "hide stereotype\n"
            "skinparam rectangle<<goal>> {\n  BackgroundColor #EDD6F0\n  BorderColor #7B3F9A\n}\n"
            "!define Rel_Access(from, to, label) from ..> to\n"
            "title Landscape\n"
            'rectangle "A Goal" <<goal>> as GOL_x\n'
            "@enduml\n"
        )

    def test_an_edit_carrying_no_body_restates_the_declarations_it_inlines(
        self, repo: Path
    ) -> None:
        from src.infrastructure.mcp import mcp_artifact_server as mcp  # noqa: PLC0415

        artifact_id = "ARC@1778000030.stale1.landscape"
        mcp.artifact_create_diagram(
            diagram_type="archimate-motivation",
            name="Landscape",
            puml=self._stale_body(artifact_id),
            artifact_id=artifact_id,
            dry_run=False,
            repo_root=str(repo),
            auto_include_stereotypes=False,
        )
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"

        mcp.artifact_edit_diagram(
            artifact_id=artifact_id, status="active", dry_run=False, repo_root=str(repo)
        )

        body = path.read_text(encoding="utf-8")
        assert "BackgroundColor #D1BADC" in body
        assert "DiagonalCorner 10" in body
        assert "!define Rel_Access(from, to, label) from -[dotted]-> to" in body
        assert body.count("skinparam rectangle<<goal>>") == 1

    def test_a_body_keeping_the_include_marker_keeps_it(self, repo: Path) -> None:
        """`auto_include_stereotypes=False` is the author choosing the marker form. An edit that
        carries no body must not convert it — expanding here left the diagram with no stereotypes
        at all and E303 refused it."""
        from src.infrastructure.mcp import mcp_artifact_server as mcp  # noqa: PLC0415

        artifact_id = "ARC@1778000031.marker1.landscape"
        mcp.artifact_create_diagram(
            diagram_type="archimate-motivation",
            name="Landscape",
            puml=(
                f"@startuml {artifact_id}\n!include ../_archimate-stereotypes.puml\n"
                "title Landscape\nrectangle X\n@enduml\n"
            ),
            artifact_id=artifact_id,
            dry_run=False,
            repo_root=str(repo),
            auto_include_stereotypes=False,
        )
        path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"

        result = mcp.artifact_edit_diagram(
            artifact_id=artifact_id, status="active", dry_run=False, repo_root=str(repo)
        )

        assert result["wrote"], result
        assert "!include ../_archimate-stereotypes.puml" in path.read_text(encoding="utf-8")


class TestNoStoredBodyDisagreesWithTheOntology:
    """The gate over real content. `--check` runs this same function in CI."""

    def test_every_diagram_body_states_what_the_ontology_declares(self) -> None:
        from src.config.workspace_paths import resolve_workspace_repo_roots  # noqa: PLC0415
        from src.infrastructure.rendering.generate_static_includes import (  # noqa: PLC0415
            stale_inlined_declarations,
        )

        roots = resolve_workspace_repo_roots(Path(__file__).resolve().parents[2])
        if not roots:
            pytest.skip("no workspace configuration; the CLI check covers this in CI")

        stale = stale_inlined_declarations(roots[0])

        assert stale == [], (
            "these diagram bodies inline a generated declaration that disagrees with the "
            f"ontology: {stale}"
        )
