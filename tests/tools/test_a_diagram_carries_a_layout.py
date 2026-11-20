"""A diagram stores a layout, reads it back, loses it without losing anything else, and is told when it is wrong.

Through the tools an author and an agent use. This stage stores and verifies a layout; nothing draws
from one yet, so the picture is PlantUML's throughout — which is what makes the forgetful map
checkable here: remove the block and every other byte of the file is as it was.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from src.application.modeling.artifact_write import generate_diagram_id
from src.application.modeling.diagram_file_format import format_diagram_puml
from src.domain.artifact_id import stable_conn_id, stable_id
from src.domain.diagrams.authored_groupings import grouping_ids
from src.domain.diagrams.layout.layout_block import read_layout
from src.domain.repository.frontmatter import body_after_frontmatter, parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}", dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, connection_type: str, target: str) -> str:
    result = mcp.artifact_add_connection(
        source_entity=source, connection_type=connection_type, target_entity=target,
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


class _View:
    """Two components, one serving the other, on a diagram of their own."""

    def __init__(self, repo: Path, **statements: object) -> None:
        self.repo = repo
        self.portal = _entity(repo, "application-component", "Portal")
        self.ledger = _entity(repo, "application-component", "Ledger")
        self.serving = stable_conn_id(_connect(repo, self.portal, "archimate-serving", self.ledger))
        self.id = generate_diagram_id("archimate-application", "A View")
        created = mcp.artifact_create_diagram(
            diagram_type="archimate-application", name="A View", artifact_id=self.id,
            entity_ids=[self.portal, self.ledger], dry_run=False, repo_root=str(repo),
            **statements,  # type: ignore[arg-type]
        )
        assert created["wrote"], created
        self.path = Path(str(created["path"]))

    @property
    def frontmatter(self) -> dict:
        return parse_frontmatter(self.path.read_text(encoding="utf-8"))

    def edit(self, *, dry_run: bool = False, **changes: object) -> dict:
        return mcp.artifact_edit_diagram(
            artifact_id=self.id, dry_run=dry_run, repo_root=str(self.repo), **changes,  # type: ignore[arg-type]
        )

    def a_layout(self) -> dict[str, object]:
        return {
            "grid": 10,
            "elements": {
                self.portal: {"x": 40, "y": 40, "w": 160, "h": 60}, stable_id(self.ledger): {"x": 400, "y": 40},
            },
            "relations": {
                self.serving: {
                    "from": {"side": "right", "at": 0.5}, "via": [[300, 70]], "label": {"at": 0.5, "dx": 0, "dy": -8},
                },
            },
            "z": {self.portal: 1},
        }

    def issues(self) -> list[dict]:
        """What verification says of the diagram as stored."""
        verified = asyncio.run(
            mcp.artifact_verify(path=str(self.path), repo_root=str(self.repo), repo_scope="engagement")
        )
        return list(verified["issues"])

    def write_frontmatter(self, **changed: object) -> None:
        """Put *changed* into the stored frontmatter by hand — what a merge or an editor outside the tools does."""
        text = self.path.read_text(encoding="utf-8")
        stated = self.frontmatter | changed
        written = format_diagram_puml(
            artifact_id=stated["artifact-id"], diagram_type=stated["diagram-type"], name=stated["name"],
            version=stated["version"], status=stated["status"], last_updated=stated["last-updated"],
            puml_body=body_after_frontmatter(text), entity_ids_used=stated.get("entity-ids-used"),
            connection_ids_used=stated.get("connection-ids-used"), manual_layout=bool(stated.get("manual-layout")),
        )
        extra = {key: stated[key] for key in ("authored-groupings", "layout") if key in stated}
        head, fence, body = written.partition("last-updated:")
        injected = yaml.safe_dump(extra, sort_keys=False) if extra else ""
        self.path.write_text(head + injected + fence + body, encoding="utf-8")


def _codes(issues: list[dict]) -> set[str]:
    return {str(issue["code"]) for issue in issues}


class TestStoringOne:
    def test_an_edit_stores_the_block_and_it_reads_back_as_stated(self, repo: Path) -> None:
        view = _View(repo)

        result = view.edit(layout=view.a_layout())

        assert result["wrote"], result
        stored = read_layout(view.frontmatter["layout"])
        assert stored == read_layout(view.a_layout())
        assert set(stored.elements) == {stable_id(view.portal), stable_id(view.ledger)}, "keyed by stable id"

    def test_a_create_stores_the_block_too(self, repo: Path) -> None:
        portal = _entity(repo, "application-component", "Portal")
        created = mcp.artifact_create_diagram(
            diagram_type="archimate-application", name="Laid Out", entity_ids=[portal],
            artifact_id=generate_diagram_id("archimate-application", "Laid Out"),
            layout={"elements": {portal: {"x": 10, "y": 20}}}, dry_run=False, repo_root=str(repo),
        )

        assert created["wrote"], created
        stored = parse_frontmatter(Path(str(created["path"])).read_text(encoding="utf-8"))["layout"]
        assert stored == {"elements": {stable_id(portal): {"x": 10, "y": 20}}}

    def test_an_edit_that_says_nothing_of_the_layout_keeps_it(self, repo: Path) -> None:
        view = _View(repo)
        view.edit(layout=view.a_layout())
        stored = view.frontmatter["layout"]

        assert view.edit(status="active")["wrote"]

        assert view.frontmatter["layout"] == stored

    def test_the_picture_is_still_plantuml_s(self, repo: Path) -> None:
        """Nothing draws from a layout yet, so storing one changes no line of the body."""
        view = _View(repo)
        body = body_after_frontmatter(view.path.read_text(encoding="utf-8"))

        view.edit(layout=view.a_layout())

        assert body_after_frontmatter(view.path.read_text(encoding="utf-8")) == body


class TestTheForgetfulMap:
    """Removing the block returns the diagram to PlantUML's arrangement with nothing else changed."""

    @pytest.mark.parametrize(
        "statements",
        [
            {},
            {"keywords": ["one", "two"]},
            {"authored_groupings": [{"label": "Front", "entity-ids": ["<portal>"]}]},
            {"authored_groupings": [{"label": "Systems", "rule": {"domain": "application"}}]},
        ],
        ids=["plain", "keywords", "listed-grouping", "ruled-grouping"],
    )
    def test_a_diagram_that_gains_a_layout_and_loses_it_is_the_diagram_it_was(
        self, repo: Path, statements: dict[str, object]
    ) -> None:
        view = _View(repo)
        if "authored_groupings" in statements:
            groupings = [
                {**group, **({"entity-ids": [view.portal]} if "entity-ids" in group else {})}
                for group in statements["authored_groupings"]  # type: ignore[union-attr]
            ]
            assert view.edit(authored_groupings=groupings)["wrote"]
        elif statements:
            assert view.edit(**statements)["wrote"]
        before = view.frontmatter | {"last-updated": None}
        body = body_after_frontmatter(view.path.read_text(encoding="utf-8"))
        boxes = {box: {"x": 0, "y": 0, "w": 300, "h": 200} for box in grouping_ids(before.get("authored-groupings"))}

        assert view.edit(layout={**view.a_layout(), "boxes": boxes})["wrote"]
        assert "layout" in view.frontmatter
        removed = view.edit(layout={})

        assert removed["wrote"], removed
        assert view.frontmatter | {"last-updated": None} == before
        assert body_after_frontmatter(view.path.read_text(encoding="utf-8")) == body


class TestRefusing:
    @pytest.mark.parametrize(
        ("block", "says"),
        [
            ({"elements": {"<portal>": {"x": 1}}}, "both x and y"),
            ({"colour": "red"}, "states colour"),
            ({"relations": {"APP_a:APP_b": {}}}, "arch-repair upgrade"),
            ({"elements": {"APP@1700000000.nobody": {"x": 1, "y": 2}}}, "does not hold"),
            ({"boxes": {"g-nosuch": {"x": 1, "y": 2}}}, "does not hold"),
            ({"relations": {"APP@1.aaaaaa---APP@2.bbbbbb@@archimate-flow": {}}}, "does not hold"),
        ],
    )
    def test_a_block_that_is_malformed_or_names_nothing_is_refused_with_a_sentence(
        self, repo: Path, block: dict[str, object], says: str
    ) -> None:
        view = _View(repo)
        if "<portal>" in (block.get("elements") or {}):  # type: ignore[operator]
            block = {"elements": {view.portal: block["elements"]["<portal>"]}}  # type: ignore[index]

        with pytest.raises(ValueError, match=says):
            view.edit(layout=block)

        assert "layout" not in view.frontmatter

    def test_a_manual_layout_diagram_takes_no_layout(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(manual_layout=True)["wrote"]

        with pytest.raises(ValueError, match="never both"):
            view.edit(layout=view.a_layout())

    def test_a_laid_out_diagram_cannot_be_made_manual_layout(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(layout=view.a_layout())["wrote"]

        with pytest.raises(ValueError, match="never both"):
            view.edit(manual_layout=True)

        assert view.edit(manual_layout=True, layout={})["wrote"], "removing the layout in the same call is allowed"


class TestAnEditThatRemovesAMember:
    """Sync reconciliation comes later; until then an edit must not leave geometry for what it removed."""

    def test_the_member_s_placement_and_its_relations_routes_go_with_it(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(layout=view.a_layout())["wrote"]

        result = view.edit(entity_ids=[view.portal])

        assert result["wrote"], result
        stored = read_layout(view.frontmatter["layout"])
        assert set(stored.elements) == {stable_id(view.portal)}
        assert not stored.relations
        assert any("Dropped from the layout" in warning for warning in result["warnings"])
        assert not _codes(view.issues()) & {"E370", "E371"}

    def test_a_removed_grouping_takes_its_box_with_it(self, repo: Path) -> None:
        view = _View(repo, authored_groupings=[{"label": "Front", "entity-ids": []}])
        assert view.edit(authored_groupings=[{"label": "Front", "entity-ids": [view.portal]}])["wrote"]
        (box,) = grouping_ids(view.frontmatter["authored-groupings"])
        assert view.edit(layout={"boxes": {box: {"x": 0, "y": 0, "w": 300, "h": 200}}, "z": {box: 2}})["wrote"]

        result = view.edit(authored_groupings=[])

        assert result["wrote"], result
        assert "layout" not in view.frontmatter


class TestGroupingIdentities:
    def test_a_grouping_is_given_an_id_and_keeps_it_when_sent_back(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(authored_groupings=[{"label": "Front", "entity-ids": [view.portal]}])["wrote"]
        (first_id,) = grouping_ids(view.frontmatter["authored-groupings"])

        renamed = [{"id": first_id, "label": "Front Office", "entity-ids": [view.portal]},
                   {"label": "Back", "entity-ids": [view.ledger]}]
        assert view.edit(authored_groupings=renamed)["wrote"]

        ids = grouping_ids(view.frontmatter["authored-groupings"])
        assert ids[0] == first_id and len(set(ids)) == 2

    def test_a_ruled_grouping_is_stored_and_drawn(self, repo: Path) -> None:
        view = _View(repo)

        result = view.edit(authored_groupings=[{"label": "Systems We Run", "rule": {"domain": "application"}}])

        assert result["wrote"], result
        (stored,) = view.frontmatter["authored-groupings"]
        assert stored["rule"] == {"domain": "application"} and stored["id"].startswith("g-")
        body = body_after_frontmatter(view.path.read_text(encoding="utf-8"))
        assert '"Systems We Run"' in body and "DOM_" not in body

    def test_a_grouping_that_is_both_listed_and_ruled_is_refused(self, repo: Path) -> None:
        view = _View(repo)

        with pytest.raises(ValueError, match="listed or ruled"):
            view.edit(authored_groupings=[
                {"label": "Both", "entity-ids": [view.portal], "rule": {"domain": "application"}},
            ])


class TestWhatVerificationSays:
    """A stored file can say what the tools would have refused: a merge wrote it, or a hand did."""

    def test_a_sound_layout_raises_nothing(self, repo: Path) -> None:
        view = _View(repo)
        sound = {
            "elements": {
                view.portal: {"x": 40, "y": 40, "w": 160, "h": 60},
                view.ledger: {"x": 400, "y": 40, "w": 160, "h": 60},
            },
            "relations": {view.serving: {"from": {"side": "right", "at": 0.5}, "to": {"side": "left", "at": 0.5}}},
        }
        assert view.edit(layout=sound)["wrote"]

        assert not _codes(view.issues()) & _LAYOUT_CODES

    def test_a_block_that_cannot_be_read_is_an_error_with_the_reader_s_sentence(self, repo: Path) -> None:
        view = _View(repo)
        view.write_frontmatter(layout={"elements": {view.portal: {"x": 1}}})

        (issue,) = [issue for issue in view.issues() if issue["code"] == "E370"]
        assert issue["severity"] == "error" and "both x and y" in issue["message"]

    def test_an_entry_naming_nothing_is_an_error(self, repo: Path) -> None:
        view = _View(repo)
        view.write_frontmatter(layout={
            "elements": {"APP@1700000000.nobody": {"x": 1, "y": 2}},
            "boxes": {"g-nosuch": {"x": 1, "y": 2}},
            "relations": {"APP@1.aaaaaa---APP@2.bbbbbb@@archimate-flow": {}},
            "z": {"occ-nobody": 1},
        })

        (issue,) = [issue for issue in view.issues() if issue["code"] == "E371"]
        assert issue["severity"] == "error" and "4 time(s)" in issue["message"]

    def test_a_layout_on_a_manual_layout_diagram_is_an_error(self, repo: Path) -> None:
        view = _View(repo)
        view.write_frontmatter(**{"manual-layout": True, "layout": {"elements": {view.portal: {"x": 1, "y": 2}}}})

        assert "E372" in _codes(view.issues())

    def test_a_grouping_without_an_id_is_an_error_naming_the_upgrade(self, repo: Path) -> None:
        view = _View(repo)
        view.write_frontmatter(**{"authored-groupings": [{"label": "Front", "entity-ids": [view.portal]}]})

        (issue,) = [issue for issue in view.issues() if issue["code"] == "E373"]
        assert issue["severity"] == "error" and "arch-repair upgrade" in issue["message"]

    def test_a_rule_nothing_satisfies_is_a_warning(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(layout={"boxes": {
            "rule:domain=application": {"x": 0, "y": 0, "w": 900, "h": 300},
            "rule:domain=strategy": {"x": 0, "y": 400, "w": 900, "h": 300},
        }})["wrote"]

        (issue,) = [issue for issue in view.issues() if issue["code"] == "W375"]
        assert issue["severity"] == "warning"
        assert "rule:domain=strategy" in issue["message"] and "rule:domain=application" not in issue["message"]

    def test_the_four_things_the_geometry_decides_are_warnings_and_do_not_refuse_the_write(self, repo: Path) -> None:
        view = _View(repo)
        wrong = {
            # Two connected elements over each other.
            "elements": {
                view.portal: {"x": 40, "y": 40, "w": 160, "h": 60},
                view.ledger: {"x": 120, "y": 60, "w": 160, "h": 60},
            },
            # Leaving sideways along the border, then back through the element it left.
            "relations": {view.serving: {"from": {"side": "right", "at": 0.5}, "via": [[200, 20], [60, 20], [60, 70]]}},
        }

        result = view.edit(layout=wrong)

        assert result["wrote"], result
        found = {issue["code"]: issue["severity"] for issue in view.issues() if issue["code"] in _LAYOUT_CODES}
        assert found == {"W376": "warning", "W377": "warning", "W378": "warning"}

    def test_a_box_over_an_element_outside_it_is_a_warning_until_the_element_is_stacked_above(self, repo: Path) -> None:
        view = _View(repo)
        assert view.edit(authored_groupings=[{"label": "Front", "entity-ids": [view.portal]}])["wrote"]
        (box,) = grouping_ids(view.frontmatter["authored-groupings"])
        hidden = {
            "elements": {
                view.portal: {"x": 40, "y": 40, "w": 160, "h": 60},
                view.ledger: {"x": 400, "y": 40, "w": 160, "h": 60},
            },
            "boxes": {box: {"x": 20, "y": 20, "w": 500, "h": 120}},
        }

        assert view.edit(layout=hidden)["wrote"]
        (issue,) = [issue for issue in view.issues() if issue["code"] == "W379"]
        assert issue["severity"] == "warning" and stable_id(view.ledger) in issue["message"]

        assert view.edit(layout={**hidden, "z": {view.ledger: 1}})["wrote"]
        assert "W379" not in _codes(view.issues())


class TestAFurtherOccurrence:
    """A stored occurrence keeps the entity it draws in the bindings block, not on itself.

    So "which instances does this diagram hold" has to be asked of the diagram as stored. Asked of
    the occurrence alone it answers none, and every statement keyed by one is refused as naming nothing.
    """

    _AGAIN = "portal-again"

    def _view(self, repo: Path) -> _View:
        view = _View(repo)
        result = view.edit(
            entity_ids=[view.portal, view.ledger],
            diagram_entities={"occurrence": [{"id": self._AGAIN, "backing_entity_id": view.portal}]},
            diagram_connections=[
                {"artifact_id": view.serving}, {"artifact_id": view.serving, "source-occurrence": self._AGAIN},
            ],
        )
        assert result["wrote"], result
        stored = view.frontmatter
        assert "backing_entity_id" not in stored["diagram-entities"]["occurrence"][0], "kept in the bindings block"
        return view

    def test_a_layout_may_place_the_occurrence_and_route_its_own_relation(self, repo: Path) -> None:
        view = self._view(repo)
        at_the_copy = f"{view.serving}@{self._AGAIN}>{stable_id(view.ledger)}"

        result = view.edit(layout={
            "elements": {self._AGAIN: {"x": 40, "y": 300, "w": 160, "h": 60}},
            "relations": {at_the_copy: {"from": {"side": "right", "at": 0.5}}, view.serving: {"via": [[300, 70]]}},
            "z": {self._AGAIN: 2},
        })

        assert result["wrote"], result
        stored = read_layout(view.frontmatter["layout"])
        assert set(stored.elements) == {self._AGAIN} and set(stored.relations) == {at_the_copy, view.serving}
        assert not _codes(view.issues()) & {"E370", "E371", "E410"}

    def test_a_label_on_the_occurrence_s_relation_is_stored_and_not_dangling(self, repo: Path) -> None:
        view = self._view(repo)
        at_the_copy = f"{view.serving}@{self._AGAIN}>{stable_id(view.ledger)}"

        result = view.edit(edge_labels={at_the_copy: "from the copy"})

        assert result["wrote"], result
        assert view.frontmatter["edge-labels"] == {at_the_copy: "from the copy"}
        assert "E410" not in _codes(view.issues())


_LAYOUT_CODES = {"E370", "E371", "E372", "E373", "W375", "W376", "W377", "W378", "W379"}
