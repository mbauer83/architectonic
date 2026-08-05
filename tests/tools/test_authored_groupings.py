"""Labelled boxes a diagram draws that the model does not hold.

The feature rendered eight live diagrams and had **no tests at all**, was reachable only by hand-
writing frontmatter — which `CLAUDE.md` forbids as a way of working — and asked the author to supply
a stereotype the membership already determines.

What is asserted here is the part a reader of the picture depends on: which box an element lands in
when it is drawn twice, what a box looks like when its members disagree about their domain, and that
a box may contain a box.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from src.application.modeling.artifact_write import generate_diagram_id
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering._authored_grouping_rendering import (
    MIXED_DOMAIN_STEREOTYPE,
    claimed_aliases,
    group_stereotype,
    resolve_authored_members,
)


def _entity(artifact_id: str, alias: str, domain: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type="goal" if domain == "motivation" else "application-component",
        name=alias,
        version="0.1.0",
        status="active",
        domain=domain,
        subdomain="",
        path=Path(f"/fake/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=alias,
        display_alias=alias,
        host_diagram_id=None,
    )


_GOAL = _entity("GOL@1000000000.AaAaAa.a-goal", "GOL_AaAaAa", "motivation")
_OTHER_GOAL = _entity("GOL@1000000001.BbBbBb.another-goal", "GOL_BbBbBb", "motivation")
_COMPONENT = _entity("APP@1000000002.CcCcCc.a-component", "APP_CcCcCc", "application")

_DOMAIN_OF = {
    "GOL_AaAaAa": "motivation",
    "GOL_BbBbBb": "motivation",
    "GOL_AaAaAa__2": "motivation",
    "APP_CcCcCc": "application",
}


def _domain_of(record: EntityRecord) -> str:
    return _DOMAIN_OF[record.display_alias]


def _stereotype_of(domain: str) -> str:
    return f"{domain.capitalize()}Grouping"


def _resolve(groups: list[dict[str, object]], entities: list[EntityRecord]):
    return resolve_authored_members(groups, entities)


class TestWhichDrawingAGroupMeans:
    """An entity drawn twice is two things to place, so membership is per drawing."""

    #: What `occurrence_entities` produces for a second drawing: same artifact id, own alias, and
    #: the occurrence id in host_diagram_id.
    _SECOND = replace(_GOAL, display_alias="GOL_AaAaAa__2", host_diagram_id="occ-2")

    def test_an_occurrence_id_names_that_drawing(self) -> None:
        (group,) = _resolve([{"label": "Second", "entity-ids": ["occ-2"]}], [_GOAL, self._SECOND])

        assert group.own_aliases() == ["GOL_AaAaAa__2"]

    def test_the_entity_id_still_names_the_original_drawing(self) -> None:
        """An index built by last-write would hand the entity id to the *last* occurrence."""
        (group,) = _resolve([{"label": "First", "entity-ids": [_GOAL.artifact_id]}], [_GOAL, self._SECOND])

        assert group.own_aliases() == ["GOL_AaAaAa"]

    def test_two_drawings_of_one_entity_sit_in_two_groups(self) -> None:
        first, second = _resolve(
            [
                {"label": "Here", "entity-ids": [_GOAL.artifact_id]},
                {"label": "There", "entity-ids": ["occ-2"]},
            ],
            [_GOAL, self._SECOND],
        )

        assert first.own_aliases() == ["GOL_AaAaAa"]
        assert second.own_aliases() == ["GOL_AaAaAa__2"]

    def test_one_drawing_belongs_to_one_group_only(self) -> None:
        first, second = _resolve(
            [
                {"label": "Here", "entity-ids": [_GOAL.artifact_id]},
                {"label": "There", "entity-ids": [_GOAL.artifact_id]},
            ],
            [_GOAL, self._SECOND],
        )

        assert first.own_aliases() == ["GOL_AaAaAa"]
        assert second.own_aliases() == []


class TestABoxInsideABox:
    def test_a_subgroup_resolves_under_its_parent(self) -> None:
        (outer,) = _resolve(
            [{
                "label": "Outer",
                "entity-ids": [_GOAL.artifact_id],
                "groups": [{"label": "Inner", "entity-ids": [_OTHER_GOAL.artifact_id]}],
            }],
            [_GOAL, _OTHER_GOAL],
        )

        assert outer.own_aliases() == ["GOL_AaAaAa"]
        assert [sub.label for sub in outer.subgroups] == ["Inner"]
        assert outer.subgroups[0].own_aliases() == ["GOL_BbBbBb"]

    def test_a_member_claimed_by_an_ancestor_is_not_repeated_inside_it(self) -> None:
        (outer,) = _resolve(
            [{
                "label": "Outer",
                "entity-ids": [_GOAL.artifact_id],
                "groups": [{"label": "Inner", "entity-ids": [_GOAL.artifact_id]}],
            }],
            [_GOAL],
        )

        assert outer.subgroups[0].own_aliases() == []

    def test_every_claimed_alias_is_reported_at_any_depth(self) -> None:
        """The renderer releases claimed members from modelled nesting; missing one re-nests it."""
        resolved = _resolve(
            [{
                "label": "Outer",
                "entity-ids": [_GOAL.artifact_id],
                "groups": [{"label": "Inner", "entity-ids": [_COMPONENT.artifact_id]}],
            }],
            [_GOAL, _COMPONENT],
        )

        assert claimed_aliases(resolved) == {"GOL_AaAaAa", "APP_CcCcCc"}

    def test_a_group_holding_only_a_populated_subgroup_is_not_empty(self) -> None:
        (outer,) = _resolve(
            [{"label": "Outer", "groups": [{"label": "Inner", "entity-ids": [_GOAL.artifact_id]}]}],
            [_GOAL],
        )

        assert not outer.is_empty()

    def test_a_group_that_resolves_to_nothing_is_empty(self) -> None:
        (outer,) = _resolve(
            [{"label": "Outer", "groups": [{"label": "Inner", "entity-ids": ["GOL@9.Ghost.gone"]}]}],
            [_GOAL],
        )

        assert outer.is_empty()


class TestWhatABoxLooksLike:
    def _stereotype(self, group) -> str:
        return group_stereotype(group, domain_of=_domain_of, stereotype_of=_stereotype_of)

    def test_members_of_one_domain_give_that_domains_look(self) -> None:
        (group,) = _resolve(
            [{"label": "Goals", "entity-ids": [_GOAL.artifact_id, _OTHER_GOAL.artifact_id]}],
            [_GOAL, _OTHER_GOAL],
        )

        assert self._stereotype(group) == "MotivationGrouping"

    def test_members_from_several_domains_give_the_grouping_look(self) -> None:
        (group,) = _resolve(
            [{"label": "Cross-cutting", "entity-ids": [_GOAL.artifact_id, _COMPONENT.artifact_id]}],
            [_GOAL, _COMPONENT],
        )

        assert self._stereotype(group) == MIXED_DOMAIN_STEREOTYPE

    def test_a_subgroups_members_count_towards_its_parents_look(self) -> None:
        """A box is one thing however deep it goes; ignoring subgroups would call this box motivation."""
        (outer,) = _resolve(
            [{
                "label": "Outer",
                "entity-ids": [_GOAL.artifact_id],
                "groups": [{"label": "Inner", "entity-ids": [_COMPONENT.artifact_id]}],
            }],
            [_GOAL, _COMPONENT],
        )

        assert self._stereotype(outer) == MIXED_DOMAIN_STEREOTYPE

    def test_an_explicit_stereotype_still_wins(self) -> None:
        (group,) = _resolve(
            [{"label": "Goals", "stereotype": "StrategyGrouping", "entity-ids": [_GOAL.artifact_id]}],
            [_GOAL],
        )

        assert self._stereotype(group) == "StrategyGrouping"


class TestTheMixedDomainLookIsDeclared:
    def test_the_generic_grouping_block_is_dashed(self) -> None:
        """Without this the mixed-domain box is indistinguishable from a plain white rectangle."""
        from src.infrastructure.rendering.generate_static_includes import _STEREOTYPE_HEADER

        block = _STEREOTYPE_HEADER.split(f"skinparam rectangle<<{MIXED_DOMAIN_STEREOTYPE}>>")[1]

        assert "BorderStyle dashed" in block.split("}")[0]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    return yaml.safe_load("\n".join(lines[1:end]))


def _body(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    return "\n".join(lines[end + 1:])


class TestReachingItThroughTheTools:
    """It could only be hand-written into the file before, which is the one way not allowed."""

    def test_create_records_and_draws_the_grouping(self, repo: Path) -> None:
        first = _make_entity(repo, "goal", "First Goal")
        second = _make_entity(repo, "goal", "Second Goal")
        diagram_id = generate_diagram_id("archimate-motivation", "Grouped View")

        created = mcp.artifact_create_diagram(
            diagram_type="archimate-motivation", name="Grouped View", artifact_id=diagram_id,
            entity_ids=[first, second],
            authored_groupings=[{"label": "The Goals", "entity-ids": [first, second]}],
            dry_run=False, repo_root=str(repo),
        )

        assert created["wrote"], created
        path = Path(str(created["path"]))
        assert _frontmatter(path)["authored-groupings"][0]["label"] == "The Goals"
        assert '"The Goals"' in _body(path)

    def test_the_look_is_derived_when_none_is_given(self, repo: Path) -> None:
        first = _make_entity(repo, "goal", "First Goal")
        diagram_id = generate_diagram_id("archimate-motivation", "Derived Look")

        created = mcp.artifact_create_diagram(
            diagram_type="archimate-motivation", name="Derived Look", artifact_id=diagram_id,
            entity_ids=[first], authored_groupings=[{"label": "The Goals", "entity-ids": [first]}],
            dry_run=False, repo_root=str(repo),
        )

        assert '<<MotivationGrouping>>' in _body(Path(str(created["path"])))

    def test_edit_adds_a_grouping_to_an_existing_diagram(self, repo: Path) -> None:
        first = _make_entity(repo, "goal", "First Goal")
        diagram_id = generate_diagram_id("archimate-motivation", "Later Grouped")
        created = mcp.artifact_create_diagram(
            diagram_type="archimate-motivation", name="Later Grouped", artifact_id=diagram_id,
            entity_ids=[first], dry_run=False, repo_root=str(repo),
        )
        path = Path(str(created["path"]))
        assert "authored-groupings" not in _frontmatter(path)

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id,
            authored_groupings=[{"label": "Added Later", "entity-ids": [first]}],
            dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _frontmatter(path)["authored-groupings"][0]["label"] == "Added Later"
        assert '"Added Later"' in _body(path)

    def test_edit_replaces_the_groupings_rather_than_merging(self, repo: Path) -> None:
        first = _make_entity(repo, "goal", "First Goal")
        diagram_id = generate_diagram_id("archimate-motivation", "Replaced Groups")
        created = mcp.artifact_create_diagram(
            diagram_type="archimate-motivation", name="Replaced Groups", artifact_id=diagram_id,
            entity_ids=[first], authored_groupings=[{"label": "Original", "entity-ids": [first]}],
            dry_run=False, repo_root=str(repo),
        )
        path = Path(str(created["path"]))

        mcp.artifact_edit_diagram(
            artifact_id=diagram_id,
            authored_groupings=[{"label": "Replacement", "entity-ids": [first]}],
            dry_run=False, repo_root=str(repo),
        )

        labels = [g["label"] for g in _frontmatter(path)["authored-groupings"]]
        assert labels == ["Replacement"]
        assert "Original" not in _body(path)

    def test_a_nested_grouping_survives_the_round_trip(self, repo: Path) -> None:
        first = _make_entity(repo, "goal", "First Goal")
        second = _make_entity(repo, "goal", "Second Goal")
        diagram_id = generate_diagram_id("archimate-motivation", "Nested View")

        created = mcp.artifact_create_diagram(
            diagram_type="archimate-motivation", name="Nested View", artifact_id=diagram_id,
            entity_ids=[first, second],
            authored_groupings=[{
                "label": "Outer", "entity-ids": [first],
                "groups": [{"label": "Inner", "entity-ids": [second]}],
            }],
            dry_run=False, repo_root=str(repo),
        )

        assert created["wrote"], created
        body = _body(Path(str(created["path"])))
        assert '"Outer"' in body
        assert '"Inner"' in body
        assert body.index('"Outer"') < body.index('"Inner"')
