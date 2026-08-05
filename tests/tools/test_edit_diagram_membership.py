"""`entity_ids` on edit means the same thing it means on create: this is what the diagram draws.

It used to mean something else. On `artifact_create_diagram` it is the membership and the body is
generated from it; on `artifact_edit_diagram` it only rewrote `entity-ids-used`, so an agent removing
an entity got a diagram that looked updated, still drew the entity, and still refused that entity's
deletion — and the next `puml="auto-sync"` recorded the reference again, because a reconcile unions
the body's entities with the frontmatter's. The workaround was to delete and recreate the diagram.

The three diagrams whose body is not the generator's to rewrite are refused instead of
half-updated, each with the operation that does work.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.application.modeling.artifact_write import generate_diagram_id
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.diagram_membership import membership_refusal
from src.infrastructure.write.artifact_write.parse_existing import ParsedDiagram


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _frontmatter(path: Path) -> dict:
    _, fm, _ = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(fm)


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def _alias(artifact_id: str) -> str:
    prefix, rest = artifact_id.split("@", 1)
    return f"{prefix}_{rest.split('.')[1]}".replace("-", "_")


def _diagram_of(repo: Path, entity_ids: list[str]) -> tuple[str, Path]:
    """A generated ArchiMate view of *entity_ids* — the kind whose body the generator owns."""
    diagram_id = generate_diagram_id("archimate-motivation", "Membership View")
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Membership View",
        artifact_id=diagram_id, entity_ids=entity_ids,
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    return diagram_id, Path(str(created["path"]))


class TestStatingTheMembership:
    def test_a_removed_member_leaves_the_frontmatter_and_the_body(self, repo: Path) -> None:
        kept = _entity(repo, "goal", "Kept Goal")
        dropped = _entity(repo, "goal", "Dropped Goal")
        diagram_id, path = _diagram_of(repo, [kept, dropped])
        assert _alias(dropped) in _body(path)

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, entity_ids=[kept], dry_run=False, repo_root=str(repo)
        )

        assert result["wrote"], result
        assert _frontmatter(path)["entity-ids-used"] == [kept]
        assert _alias(dropped) not in _body(path)
        assert _alias(kept) in _body(path)

    def test_the_removal_survives_an_auto_sync(self, repo: Path) -> None:
        """The trap: a reconcile unions the body's entities back in, undoing a frontmatter-only edit."""
        kept = _entity(repo, "goal", "Kept Goal")
        dropped = _entity(repo, "goal", "Dropped Goal")
        diagram_id, path = _diagram_of(repo, [kept, dropped])
        mcp.artifact_edit_diagram(
            artifact_id=diagram_id, entity_ids=[kept], dry_run=False, repo_root=str(repo)
        )

        synced = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml="auto-sync", dry_run=False, repo_root=str(repo)
        )

        assert synced["wrote"], synced
        assert _frontmatter(path)["entity-ids-used"] == [kept]

    def test_a_member_can_be_added(self, repo: Path) -> None:
        first = _entity(repo, "goal", "First Goal")
        second = _entity(repo, "goal", "Second Goal")
        diagram_id, path = _diagram_of(repo, [first])

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, entity_ids=[first, second], dry_run=False, repo_root=str(repo)
        )

        assert result["wrote"], result
        assert set(_frontmatter(path)["entity-ids-used"]) == {first, second}
        assert _alias(second) in _body(path)

    def test_it_composes_with_the_rest_of_the_edit(self, repo: Path) -> None:
        """A membership change is part of one write, so nothing else the call carries is dropped."""
        kept = _entity(repo, "goal", "Kept Goal")
        dropped = _entity(repo, "goal", "Dropped Goal")
        diagram_id, path = _diagram_of(repo, [kept, dropped])

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, entity_ids=[kept], version="0.2.0",
            dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        fm = _frontmatter(path)
        assert fm["entity-ids-used"] == [kept]
        assert fm["version"] == "0.2.0"

    def test_a_dry_run_writes_nothing(self, repo: Path) -> None:
        kept = _entity(repo, "goal", "Kept Goal")
        dropped = _entity(repo, "goal", "Dropped Goal")
        diagram_id, path = _diagram_of(repo, [kept, dropped])

        mcp.artifact_edit_diagram(
            artifact_id=diagram_id, entity_ids=[kept], dry_run=True, repo_root=str(repo)
        )

        assert set(_frontmatter(path)["entity-ids-used"]) == {kept, dropped}


class TestWhenTheBodyIsNotTheGeneratorsToRewrite:
    def test_a_manual_layout_diagram_is_refused_with_the_alternative(self, repo: Path) -> None:
        kept = _entity(repo, "goal", "Kept Goal")
        dropped = _entity(repo, "goal", "Dropped Goal")
        diagram_id, path = _diagram_of(repo, [kept, dropped])
        assert mcp.artifact_edit_diagram(
            artifact_id=diagram_id, manual_layout=True, dry_run=False, repo_root=str(repo)
        )["wrote"]

        with pytest.raises(ValueError, match="manual-layout"):
            mcp.artifact_edit_diagram(
                artifact_id=diagram_id, entity_ids=[kept], dry_run=False, repo_root=str(repo)
            )

        assert set(_frontmatter(path)["entity-ids-used"]) == {kept, dropped}

    def test_the_refusal_names_what_to_do_instead(self, repo: Path) -> None:
        kept = _entity(repo, "goal", "Kept Goal")
        diagram_id, _ = _diagram_of(repo, [kept])
        mcp.artifact_edit_diagram(
            artifact_id=diagram_id, manual_layout=True, dry_run=False, repo_root=str(repo)
        )

        with pytest.raises(ValueError, match="puml"):
            mcp.artifact_edit_diagram(
                artifact_id=diagram_id, entity_ids=[kept], dry_run=False, repo_root=str(repo)
            )


class TestSupplyingABodyIsADifferentRequest:
    def test_puml_with_entity_ids_still_takes_the_callers_body(self, repo: Path) -> None:
        """Unchanged behaviour: the caller supplies both the picture and the membership."""
        first = _entity(repo, "goal", "First Goal")
        second = _entity(repo, "goal", "Second Goal")
        diagram_id, path = _diagram_of(repo, [first, second])
        hand_written = (
            f"@startuml {diagram_id}\n\ntitle Membership View\n\n"
            f'rectangle "First Goal" <<Goal>> as {_alias(first)}\n\n@enduml\n'
        )

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=hand_written, entity_ids=[first], connection_ids=[],
            dry_run=False, repo_root=str(repo),
        )

        assert result["wrote"], result
        assert _frontmatter(path)["entity-ids-used"] == [first]
        assert _alias(second) not in _body(path)


class TestWhichDiagramsOwnTheirMembershipElsewhere:
    """The two remaining refusals, over the rule directly — building a projector-owned diagram
    through the tools would test the diagram type, not the rule."""

    def _parsed(self, frontmatter: dict, bindings: list | None = None) -> ParsedDiagram:
        return ParsedDiagram(
            frontmatter=frontmatter, puml_body="", raw_text="",
            bindings=bindings or [], view_derivations=[],
        )

    def test_a_generated_archimate_view_is_allowed(self) -> None:
        assert membership_refusal(self._parsed({"entity-ids-used": []})) is None

    def test_a_standalone_diagram_is_pointed_at_diagram_entities(self) -> None:
        refusal = membership_refusal(self._parsed({"diagram-entities": {"step": []}}))

        assert refusal is not None
        assert "diagram_entities" in refusal

    def test_a_model_backed_diagram_is_pointed_at_its_binding(self) -> None:
        refusal = membership_refusal(
            self._parsed({"diagram-entities": {"_scope_entity_id": "APP@1.AbcDef.thing"}})
        )

        assert refusal is not None
        assert "scoped-by" in refusal

    def test_a_manual_layout_diagram_is_pointed_at_puml(self) -> None:
        refusal = membership_refusal(self._parsed({"manual-layout": True}))

        assert refusal is not None
        assert "puml" in refusal
