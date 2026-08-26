"""A refresh brings a diagram's references to the spellings their artifacts currently have.

Identity is the ``PREFIX@epoch.random`` stem, so a reference naming a former title resolves forever
and no read fails. The cost is entirely on a reader — the slug is the only part of an id a human
interprets — and it accumulates silently, because nothing that *uses* the reference repairs it.

**The reconcile path already did this and the refresh path did not**, which is the whole defect.
`sync_diagram_to_model` resolves each id to its record and writes `record.artifact_id`, so a stale
spelling is corrected as a side effect. The scope-bound and standalone branches of `refresh_diagram`
call `edit_diagram` without the reference lists at all, so `entity-ids-used` survives byte for byte —
stale slug included. The verifier reports it as W305, and the only thing that cleared it was resending
the whole `puml` body of a manual-layout diagram: thirteen kilobytes of hand-laid layout to correct
seventy-eight characters of frontmatter.

**Spellings only — never membership.** This path must not add or drop a reference: a standalone
diagram's `entity-ids-used` is authored, and re-deriving it from the body is exactly the inference the
membership contract refuses. An id whose stem resolves to nothing is left alone rather than removed,
for the same reason: a refresh has never deleted a reference and must not start.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.write.artifact_write import diagram_sync
from src.infrastructure.write.artifact_write._sync_helpers import current_reference_spellings
from src.infrastructure.write.artifact_write.diagram_sync import refresh_diagram
from src.infrastructure.write.artifact_write.types import WriteResult
from tests.tools.test_scope_bound_refresh import (  # noqa: PLC2701
    _fresh_store,
    _make_app_entity,
    _make_context,
    repo,  # noqa: F401  — the fixture
)


def _stale(artifact_id: str, slug: str) -> str:
    """The same artifact, spelled with a slug it no longer has."""
    stem, _sep, _slug = artifact_id.rpartition(".")
    return f"{stem}.{slug}"


def _alias(artifact_id: str) -> str:
    """The display alias a body declares for this entity: prefix and the rename-stable random part.

    The body has to declare it or the diagram is not valid at all — `entity-ids-used` naming an entity
    the body does not draw is E309, whatever the slug says. A first version of these fixtures left the
    body empty, so every one of them was an invalid diagram and the write was rolled back before the
    spelling could be looked at.
    """
    prefix, _at, rest = artifact_id.partition("@")
    return f"{prefix}_{rest.split('.')[1]}"


def _body(name: str, *entity_ids: str) -> str:
    """A body drawing each entity under its display alias, which is what makes the diagram valid.

    The visible title is not decoration: a diagram without one is E308, and these fixtures have to be
    diagrams the product accepts, or the write is rolled back before the spelling is ever looked at.
    """
    boxes = "\n".join(f'rectangle "{eid.rsplit(".", 1)[1]}" as {_alias(eid)}' for eid in entity_ids)
    return f"@startuml {name}\ntitle {name}\n{boxes}\n@enduml"


def _standalone_naming(repo_root: Path, entity_id: str) -> str:
    """A standalone diagram naming *entity_id*, in the shape this repository's C4 views actually have.

    `diagram-entities: {{}}` with a populated `entity-ids-used` is what the shipped c4-component views
    carry, and it is what routes a diagram down the standalone branch of `refresh_diagram` — the one
    that keeps the stored body and, until now, kept its reference spellings exactly as they were.
    """
    artifact_id = "DIA@1777000020.tslug.stale-reference"
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "Stale Reference"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used:
- {entity_id}
connection-ids-used: []
diagram-entities: {{}}
---
{_body("stale-reference", entity_id)}
"""
    path = repo_root / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


def _refresh(repo_root: Path, artifact_id: str) -> None:
    verifier, clear_caches = _make_context(repo_root)
    refresh_diagram(
        repo_root=repo_root,
        store=_fresh_store(repo_root),
        verifier=verifier,
        clear_repo_caches=clear_caches,
        artifact_id=artifact_id,
        dry_run=False,
    )


class TestTheSpellingsAReferenceListShouldHave:
    """`current_reference_spellings` is the correction itself, stated directly.

    Directly, because a whole diagram is a poor witness for it: a fixture has to satisfy the renderer,
    the stereotype includes and the alias rules before the frontmatter is ever looked at, and a
    fixture that fails any of those is rolled back — which looks exactly like a correction that did
    not happen. The wiring is asserted separately, on the arguments the refresh hands on.
    """

    def test_a_stale_slug_becomes_the_current_one(self, repo: Path) -> None:  # noqa: F811
        real = _make_app_entity(repo, "Planning Data Carries Its Own Lineage")
        stale = _stale(real, "manufacturing-planning-runs-nightly")

        assert current_reference_spellings([stale], _fresh_store(repo)) == [real]

    def test_a_reference_already_current_is_returned_unchanged(self, repo: Path) -> None:  # noqa: F811
        real = _make_app_entity(repo, "Planning Data Carries Its Own Lineage")

        assert current_reference_spellings([real], _fresh_store(repo)) == [real]

    def test_an_id_that_resolves_to_nothing_is_kept(self, repo: Path) -> None:  # noqa: F811
        """A refresh has never deleted a reference, and correcting spellings must not make it start:
        an id whose stem names no artifact is a question for the author, not a line to remove."""
        gone = "APP@1700000000.gone00.an-entity-that-does-not-exist"

        assert current_reference_spellings([gone], _fresh_store(repo)) == [gone]

    def test_the_order_and_the_count_the_author_wrote_are_kept(self, repo: Path) -> None:  # noqa: F811
        """Spellings only. Re-deriving membership here would be the inference the membership contract
        refuses, and reordering would churn every diagram's frontmatter on every refresh."""
        second = _make_app_entity(repo, "Zebra System")
        first = _make_app_entity(repo, "Alpha System")
        gone = "APP@1700000000.gone00.an-entity-that-does-not-exist"

        given = [second, gone, first]

        assert current_reference_spellings(given, _fresh_store(repo)) == given

    def test_an_empty_list_stays_empty(self, repo: Path) -> None:  # noqa: F811
        assert current_reference_spellings([], _fresh_store(repo)) == []


class TestWhatTheRefreshHandsOn:
    """The wiring: a refresh of a standalone or scope-bound diagram now passes the reference lists.

    It passed neither, which is the defect — `entity-ids-used` survived byte for byte, so a stale slug
    stayed wrong forever. The reconcile branch has always corrected them, as a side effect of resolving
    each id to its record, which is why the same repository heals one diagram and not another.
    """

    def _captured(self, repo_root: Path, artifact_id: str, monkeypatch) -> dict:  # noqa: ANN001
        captured: dict = {}

        def spy(**kwargs: object):  # noqa: ANN202
            captured.update(kwargs)
            return WriteResult(
                wrote=True, path=Path("d.puml"), artifact_id=artifact_id, content=None,
                warnings=[], verification={"path": "d.puml", "file_type": "diagram", "valid": True, "issues": []},
            )

        monkeypatch.setattr(diagram_sync, "edit_diagram", spy)
        verifier, clear_caches = _make_context(repo_root)
        refresh_diagram(
            repo_root=repo_root, store=_fresh_store(repo_root), verifier=verifier,
            clear_repo_caches=clear_caches, artifact_id=artifact_id, dry_run=False,
        )
        return captured

    def test_a_stale_slug_reaches_the_write_already_corrected(self, repo: Path, monkeypatch) -> None:  # noqa: F811, ANN001
        real = _make_app_entity(repo, "Planning Data Carries Its Own Lineage")
        diag = _standalone_naming(repo, _stale(real, "manufacturing-planning-runs-nightly"))

        captured = self._captured(repo, diag, monkeypatch)

        assert captured["entity_ids_used"] == [real]

    def test_the_connection_list_is_carried_too(self, repo: Path, monkeypatch) -> None:  # noqa: F811, ANN001
        """Both lists or neither: a connection id is two entity ids joined, and it goes stale the same
        way. Passing only the entity list would heal half a diagram."""
        real = _make_app_entity(repo, "Planning Data Carries Its Own Lineage")
        diag = _standalone_naming(repo, real)

        captured = self._captured(repo, diag, monkeypatch)

        assert captured["connection_ids_used"] == []

    def test_the_body_is_still_left_to_the_renderer(self, repo: Path, monkeypatch) -> None:  # noqa: F811, ANN001
        """No `puml` is passed, so this remains a re-render from stored state rather than becoming a
        body replacement — which would discard a hand-laid layout."""
        real = _make_app_entity(repo, "Planning Data Carries Its Own Lineage")
        diag = _standalone_naming(repo, real)

        captured = self._captured(repo, diag, monkeypatch)

        assert "puml" not in captured
        assert captured["rebuild_layout"] is True
