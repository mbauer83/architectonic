"""An edit that replaces a diagram's body records the relations that body draws, and no others.

`connection-ids-used` is a **query** surface — it is how "which views show this connection" is
answered, which is impact analysis, the reason the tool exists. A diagram claiming to draw a relation
it does not draw corrupts that answer, and the claim was arriving by itself: the stored value was
unioned with what the new body drew, so a connection the body stopped drawing kept its reference.

**Measured before it was fixed**, on a pair carrying both a composition and a serving: a supplied
body drawing only the serving kept both references, and a body drawing only the composition kept both
as well. `puml="auto-sync"` restores consistency by *redrawing* the missing edge, not by dropping the
reference, so there was no existing reconcile to copy — the report's claim that one existed is why
this was re-checked rather than assumed.

Stated over **both** ways a body arrives, because both ended by carrying a stored value across a
replacement and they differ only in how the fresh set was obtained. And with the negatives that make
it honest: inference is not omniscient, so a pair it cannot decide keeps its references, and nesting
two levels deep still draws the pair it nests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    ensure_arch_repo_defaults(root)
    return root


def _entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="application-component", name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, connection_type: str) -> str:
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=connection_type,
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _recorded_connections(path: Path) -> list[str]:
    """Read through the frontmatter's one owner: a connection id itself carries `---`."""
    return list(parse_frontmatter(path.read_text(encoding="utf-8")).get("connection-ids-used") or [])


def _alias(entity_id: str) -> str:
    return f"APP_{entity_id.split('.')[1]}"


@pytest.fixture()
def pair_drawing_both(repo: Path) -> tuple[Path, str, str, str, str, str]:
    """A diagram of one pair that the model joins twice — a composition and a serving."""
    source, target = _entity(repo, "Order Service"), _entity(repo, "Order Store")
    composition = _connect(repo, source, target, "archimate-composition")
    serving = _connect(repo, source, target, "archimate-serving")
    created = mcp.artifact_create_diagram(
        name="Pair", diagram_type="archimate-application", entity_ids=[source, target],
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    path = Path(str(created["path"]))
    assert sorted(_recorded_connections(path)) == sorted([composition, serving])
    return path, str(created["artifact_id"]), source, target, composition, serving


class TestABodySuppliedAsPuml:
    def test_drawing_one_of_two_records_one(
        self, repo: Path, pair_drawing_both: tuple[Path, str, str, str, str, str]
    ) -> None:
        path, diagram_id, source, target, _composition, serving = pair_drawing_both
        body = (
            f"@startuml pair\n"
            f'rectangle "Order Service" <<application_component>> as {_alias(source)}\n'
            f'rectangle "Order Store" <<application_component>> as {_alias(target)}\n'
            f"{_alias(source)} --> {_alias(target)}\n"
            f"@enduml"
        )

        assert mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=body, dry_run=False, repo_root=str(repo)
        )["wrote"]

        assert _recorded_connections(path) == [serving]

    def test_drawing_the_other_one_records_the_other(
        self, repo: Path, pair_drawing_both: tuple[Path, str, str, str, str, str]
    ) -> None:
        """Nesting draws a relation without any arrow, so the two directions must both work."""
        path, diagram_id, source, target, composition, _serving = pair_drawing_both
        body = (
            f"@startuml pair\n"
            f'rectangle "Order Service" <<application_component>> as {_alias(source)} {{\n'
            f'  rectangle "Order Store" <<application_component>> as {_alias(target)}\n'
            f"}}\n@enduml"
        )

        assert mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=body, dry_run=False, repo_root=str(repo)
        )["wrote"]

        assert _recorded_connections(path) == [composition]

    def test_an_ambiguous_relation_keeps_every_reference_for_its_pair(self, repo: Path) -> None:
        """Inference stays silent on purpose where a drawn glyph fits more than one connection.

        A bare arrow between a pair the model joins with both a composition and an aggregation
        resolves to neither, so both references are kept. Treating "I could not name it" as "the body
        does not draw it" would drop one of them, and which one would depend on the glyph.
        """
        source, target = _entity(repo, "Order Service"), _entity(repo, "Order Store")
        composition = _connect(repo, source, target, "archimate-composition")
        aggregation = _connect(repo, source, target, "archimate-aggregation")
        created = mcp.artifact_create_diagram(
            name="Ambiguous", diagram_type="archimate-application", entity_ids=[source, target],
            dry_run=False, repo_root=str(repo),
        )
        path, diagram_id = Path(str(created["path"])), str(created["artifact_id"])
        body = (
            f"@startuml ambiguous\n"
            f'rectangle "Order Service" <<application_component>> as {_alias(source)}\n'
            f'rectangle "Order Store" <<application_component>> as {_alias(target)}\n'
            f"{_alias(source)} --> {_alias(target)}\n@enduml"
        )

        result = mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=body, dry_run=False, repo_root=str(repo)
        )
        assert result["wrote"], result

        assert sorted(_recorded_connections(path)) == sorted([composition, aggregation])

    def test_nesting_two_levels_deep_still_draws_the_pair_it_nests(self, repo: Path) -> None:
        """`_containment_relations` reads one level — the level the completeness rules compare.

        A body nesting the innermost element two levels down states that the outermost contains it,
        so a stored composition between that pair is drawn and must survive. Reading one level would
        have taken it to be undrawn and dropped it.
        """
        outer, middle, inner = (
            _entity(repo, "Platform"), _entity(repo, "Order Service"), _entity(repo, "Order Store")
        )
        _connect(repo, outer, middle, "archimate-composition")
        _connect(repo, middle, inner, "archimate-composition")
        spanning = _connect(repo, outer, inner, "archimate-composition")
        created = mcp.artifact_create_diagram(
            name="Nested", diagram_type="archimate-application",
            entity_ids=[outer, middle, inner], dry_run=False, repo_root=str(repo),
        )
        path, diagram_id = Path(str(created["path"])), str(created["artifact_id"])
        body = (
            f"@startuml nested\n"
            f'rectangle "Platform" <<application_component>> as {_alias(outer)} {{\n'
            f'  rectangle "Order Service" <<application_component>> as {_alias(middle)} {{\n'
            f'    rectangle "Order Store" <<application_component>> as {_alias(inner)}\n'
            f"  }}\n}}\n@enduml"
        )

        assert mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=body, dry_run=False, repo_root=str(repo)
        )["wrote"]

        assert spanning in _recorded_connections(path)

    def test_a_containment_reference_whose_nesting_was_removed_is_dropped(self, repo: Path) -> None:
        """The other half of the same rule, and the one an exemption for nesting would have spared."""
        outer, inner = _entity(repo, "Platform"), _entity(repo, "Order Service")
        composition = _connect(repo, outer, inner, "archimate-composition")
        created = mcp.artifact_create_diagram(
            name="Flat", diagram_type="archimate-application", entity_ids=[outer, inner],
            dry_run=False, repo_root=str(repo),
        )
        path, diagram_id = Path(str(created["path"])), str(created["artifact_id"])
        assert _recorded_connections(path) == [composition]
        body = (
            f"@startuml flat\n"
            f'rectangle "Platform" <<application_component>> as {_alias(outer)}\n'
            f'rectangle "Order Service" <<application_component>> as {_alias(inner)}\n@enduml'
        )

        assert mcp.artifact_edit_diagram(
            artifact_id=diagram_id, puml=body, dry_run=False, repo_root=str(repo)
        )["wrote"]

        assert _recorded_connections(path) == []


class TestTheReconcileItself:
    """The rule, unit-level, including the branch a rendered body takes.

    Both ways a body arrives hand the same question to this one function; they differ only in the
    evidence they bring. A rendered body brings what the renderer drew and nothing it was unsure
    about, which is why the rendered branch needs no competence rule of its own.
    """

    def _reconcile(self, **kwargs: object) -> list[str] | None:
        from src.infrastructure.write.artifact_write.diagram_references import (
            reconcile_recorded_connections,
        )

        return reconcile_recorded_connections(**kwargs)  # type: ignore[arg-type]

    def test_a_rendered_body_replaces_the_stored_value(self) -> None:
        kept = self._reconcile(
            caller_supplied=None,
            stored=["A@1.a---B@1.b@@archimate-composition", "A@1.a---B@1.b@@archimate-serving"],
            drawn=["A@1.a---B@1.b@@archimate-serving"],
            drawn_entity_ids=["A@1.a", "B@1.b"],
        )

        assert kept == ["A@1.a---B@1.b@@archimate-serving"]

    def test_a_callers_own_argument_is_never_dropped(self) -> None:
        """Merge is right for caller input; only the stored value is reconciled."""
        kept = self._reconcile(
            caller_supplied=["A@1.a---B@1.b@@archimate-composition"],
            stored=["A@1.a---B@1.b@@archimate-serving"],
            drawn=[],
            drawn_entity_ids=["A@1.a", "B@1.b"],
        )

        assert kept == ["A@1.a---B@1.b@@archimate-composition"]

    def test_a_pair_the_reader_could_not_decide_keeps_its_references(self) -> None:
        """An ambiguous untyped relation stays uninferred on purpose, and says so."""
        kept = self._reconcile(
            caller_supplied=None,
            stored=["A@1.a---B@1.b@@archimate-composition"],
            drawn=[],
            drawn_entity_ids=["A@1.a", "B@1.b"],
            undecided_pairs=frozenset({frozenset({"A@1.a", "B@1.b"})}),
        )

        assert kept == ["A@1.a---B@1.b@@archimate-composition"]

    def test_an_endpoint_the_body_does_not_declare_keeps_its_references(self) -> None:
        kept = self._reconcile(
            caller_supplied=None,
            stored=["A@1.a---C@1.c@@archimate-serving"],
            drawn=[],
            drawn_entity_ids=["A@1.a", "B@1.b"],
        )

        assert kept == ["A@1.a---C@1.c@@archimate-serving"]

    def test_a_malformed_reference_is_left_for_whoever_diagnoses_it(self) -> None:
        kept = self._reconcile(
            caller_supplied=None, stored=["not-a-connection-id"], drawn=[],
            drawn_entity_ids=["A@1.a"],
        )

        assert kept == ["not-a-connection-id"]

    def test_no_stored_value_is_the_create_path_and_merges(self) -> None:
        kept = self._reconcile(
            caller_supplied=["A@1.a---B@1.b@@archimate-serving"], stored=None,
            drawn=["A@1.a---B@1.b@@archimate-composition"], drawn_entity_ids=["A@1.a", "B@1.b"],
        )

        assert kept == [
            "A@1.a---B@1.b@@archimate-serving", "A@1.a---B@1.b@@archimate-composition",
        ]
