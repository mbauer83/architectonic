"""An artifact whose title the reader typed comes back first, whatever kind it is.

Measured on the served repository before this existed: querying a scratchpad note's exact title
returned it in the **reserved last slot** — rank 12 of 12 at `limit=12`, rank 19 of 20 at `limit=20` —
below eleven artifacts containing none of the phrase. The note was reachable only because 0.7.1 added
a floor that keeps subordinate kinds from being starved out of the window entirely; without it the
answer contained nothing the reader had asked for.

The cause is not a bad score. Per-table bm25 and the token-match supplement are on scales that say
nothing about each other, which is exactly why `_rank_balanced` ranks within a kind and round-robins
across kinds rather than sorting globally. There is no common axis to boost on, and inventing one
undoes the reason the round-robin exists.

So the answer is not a score at all. *The title equals the query* and *every query term appears in the
title* are booleans, computed identically for every kind, and comparable where the scores are not.
They sit above the round-robin without touching its premise:

1. **exact** — the normalised title equals the normalised query. Any kind, no exceptions.
2. **all terms** — every query term appears in the title. Any kind.
3. the existing per-kind round-robin over everything else.

Two properties are load-bearing and each has its own test below.

**Tiers 1 and 2 are kind-blind.** An artifact whose title the reader typed exactly is not a
half-formed thought, whatever kind it is, so subordination applies inside tier 3 only.

**A tier round-robins across kinds too.** Ordering a tier by kind — all entities, then all diagrams —
would reproduce a defect this project already shipped, measured and reverted: `prioritize_global_hits`
records that a document scoring 9.0 came back below an entity scoring 7.0, and that "with a window of
twenty and forty entity hits, a diagram could not appear at all". Tier 2 is routinely larger than the
window (measured: 66 entity titles contain "assurance" against 8 diagram and 3 document titles), so a
kind-ordered tier 2 would show no diagram at all for a one-word query.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts._search import search_artifacts
from src.domain.ontology_representation.artifact_types import (
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
)

_QUERY = "sketch before naming a type"


def _entity(n: int, name: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=f"APP@{n}", artifact_type="application-component", name=name,
        version="0.1.0", status="active", domain="application", subdomain="", path=Path("e.md"),
        keywords=(), extra={}, content_text=name, display_blocks={}, display_label=name,
        display_alias=f"APP{n}",
    )


def _diagram(n: int, name: str) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=f"ARC@{n}", artifact_type="diagram", name=name,
        diagram_type="archimate-layered", version="0.1.0", status="draft", path=Path("d.puml"),
        extra={},
    )


def _document(n: int, title: str, *, content: str | None = None) -> DocumentRecord:
    return DocumentRecord(
        artifact_id=f"ADR@{n}", doc_type="adr", title=title, status="draft", path=Path("c.md"),
        keywords=(), sections=(), content_text=content if content is not None else title, extra={},
    )


def _note(n: int, title: str, *, body: str = "") -> ScratchpadNoteRecord:
    return ScratchpadNoteRecord(
        artifact_id=f"SCR@1.pad#note/n{n}", scratchpad_id="SCR@1.pad", scratchpad_name="Q3 thinking",
        note_id=f"n{n}", title=title, body=body, element_type="", domain="", status="draft",
        path=Path("pad.yaml"), area="",
    )


class _Store:
    """A fixture population, with FTS off so the scored path runs and the test owns the scores."""

    def __init__(self, *, entities=(), diagrams=(), documents=(), notes=()) -> None:
        self._entities = list(entities)
        self._diagrams = list(diagrams)
        self._documents = list(documents)
        self._notes = list(notes)

    def search_fts(self, query, **kwargs):  # noqa: ANN001, ANN003, ARG002
        return []

    def list_entities(self):
        return list(self._entities)

    def list_connections(self):
        return []

    def list_diagrams(self):
        return list(self._diagrams)

    def list_documents(self):
        return list(self._documents)

    def list_scratchpad_notes(self):
        return list(self._notes)


    def list_scratchpads_indexed(self, **kwargs):  # noqa: ANN003, ARG002
        return []

    def get_scratchpad(self, artifact_id: str):  # noqa: ANN001, ARG002
        return None
    def entity_ids(self):
        return [r.artifact_id for r in self._entities]

    def get_entity(self, artifact_id):  # noqa: ANN001
        return next((r for r in self._entities if r.artifact_id == artifact_id), None)

    def get_connection(self, artifact_id):  # noqa: ANN001
        return None

    def get_diagram(self, artifact_id):  # noqa: ANN001
        return next((r for r in self._diagrams if r.artifact_id == artifact_id), None)

    def get_document(self, artifact_id):  # noqa: ANN001
        return next((r for r in self._documents if r.artifact_id == artifact_id), None)

    def get_scratchpad_note(self, artifact_id):  # noqa: ANN001
        return next((r for r in self._notes if r.artifact_id == artifact_id), None)


def _ranked(store: _Store, query: str = _QUERY, limit: int = 12) -> list[str]:
    return [h.record.artifact_id for h in search_artifacts(store, None, query, limit=limit).hits]


class TestAnExactTitleComesFirst:
    def test_a_note_whose_title_is_the_query_ranks_first(self) -> None:
        """The measured defect. It ranked 12 of 12, in the slot the floor reserved for it."""
        store = _Store(
            entities=[_entity(n, f"typing a sketch {n}") for n in range(20)],
            notes=[_note(1, "Sketch before naming a type")],
        )

        assert _ranked(store)[0] == "SCR@1.pad#note/n1"

    def test_an_entity_whose_name_is_the_query_still_ranks_first(self) -> None:
        store = _Store(entities=[_entity(n, f"sketching type {n}") for n in range(20)] + [_entity(99, _QUERY)])

        assert _ranked(store)[0] == "APP@99"

    def test_two_exact_matches_of_different_kinds_are_adjacent_at_the_top(self) -> None:
        """`Promote Artifacts` names an entity *and* a diagram in the live repository."""
        store = _Store(
            entities=[_entity(n, f"sketch {n}") for n in range(20)] + [_entity(99, _QUERY)],
            diagrams=[_diagram(99, "Sketch Before Naming A Type")],
        )

        assert set(_ranked(store)[:2]) == {"APP@99", "ARC@99"}

    def test_matching_ignores_case_and_punctuation(self) -> None:
        store = _Store(documents=[_document(1, "Sketch, before naming a TYPE!")])

        assert _ranked(store)[0] == "ADR@1"


class TestEveryTermInTheTitle:
    """The second section, and it runs across kinds like the first.

    Weaker evidence than an exact title, but still evidence the reader meant *this* artifact rather
    than something whose body happened to mention the words. It sits above the scored section for
    every kind, which is what makes a scratchpad reachable when someone half-remembers its name.

    What it does **not** do is suspend subordination for the scored section below it, and it cannot
    lift a subordinate kind above a preference — both asserted here, because building this section
    kind-blind is what broke them the first time.
    """

    def test_a_title_carrying_every_term_outranks_a_body_match_of_another_kind(self) -> None:
        store = _Store(
            entities=[_entity(n, f"unrelated {n}") for n in range(20)],
            documents=[_document(1, "Naming a type: sketch before you commit")],
        )

        assert _ranked(store)[0] == "ADR@1"

    def test_an_exact_title_outranks_a_title_carrying_every_term(self) -> None:
        store = _Store(
            documents=[_document(1, "Naming a type: sketch before you commit")],
            notes=[_note(1, "Sketch before naming a type")],
        )

        assert _ranked(store)[:2] == ["SCR@1.pad#note/n1", "ADR@1"]

    def test_a_note_carrying_every_term_is_ranked_with_the_rest(self) -> None:
        """A note whose title carries what the reader typed is in the same section as the entities
        whose titles do. That is the change B63 makes deliberately: subordination applies to the
        section reached on *similarity*, not to one reached by naming the thing."""
        store = _Store(
            entities=[_entity(n, f"Chameleon {n}") for n in range(4)],
            notes=[_note(1, "Chameleon onboarding")],
        )

        kinds = [h.record_type for h in search_artifacts(store, None, "chameleon", limit=10).hits]

        assert "scratchpad-note" in kinds[:2]

    def test_a_note_matching_only_in_its_body_still_comes_last(self) -> None:
        """The half of subordination that is unchanged, and the reason the case above is not a
        weakening: a note that merely mentions the words is still drawn after everything."""
        store = _Store(
            entities=[_entity(n, f"Chameleon {n}") for n in range(4)],
            notes=[_note(1, "Something else entirely", body="chameleon " * 20)],
        )

        kinds = [h.record_type for h in search_artifacts(store, None, "chameleon", limit=10).hits]

        assert kinds[-1] == "scratchpad-note"
        assert all(kind != "scratchpad-note" for kind in kinds[:-1])


class TestNoKindIsStarved:
    def test_a_query_many_titles_match_still_shows_every_matching_kind(self) -> None:
        """The defect a kind-ordered promotion would reproduce, at the size it reproduces it.

        Sixty entities and three diagrams all carry both query terms in their titles. Drawn by kind,
        a window of twelve would be sixty entities deep before the first diagram — which is the
        sentence `prioritize_global_hits` records having already shipped once.
        """
        store = _Store(
            entities=[_entity(n, f"assurance component {n}") for n in range(60)],
            diagrams=[_diagram(n, f"assurance component view {n}") for n in range(3)],
        )

        kinds = {h.record_type for h in search_artifacts(store, None, "assurance component", limit=12).hits}

        assert kinds == {"entity", "diagram"}

    def test_many_exact_matches_of_one_kind_do_not_crowd_out_another(self) -> None:
        """The promotion is kind-blind, so it round-robins too."""
        store = _Store(
            entities=[_entity(n, _QUERY) for n in range(30)],
            diagrams=[_diagram(1, _QUERY)],
        )

        assert "diagram" in {h.record_type for h in search_artifacts(store, None, _QUERY, limit=4).hits}


class TestNothingElseMoves:
    def test_a_query_matching_no_title_is_ranked_exactly_as_before(self) -> None:
        """The regression that matters most: with no tier match, tiering must change nothing."""
        store = _Store(
            entities=[_entity(n, f"component {n}") for n in range(10)],
            documents=[_document(1, "Something else entirely")],
        )

        assert _ranked(store, "component", limit=12) == _expected_round_robin(store, "component", 12)

    def test_an_empty_query_is_left_exactly_as_it_was(self) -> None:
        """An empty query matches *everything* today — `token_match_score` gives full weight because
        `"" in field` is true — and that is pre-existing behaviour this change does not touch.

        What is asserted is the invariant: no title can be "equal to" an empty query and no term can
        "appear in" a title when there are no terms, so every hit lands in tier 3 and the ranking is
        the one it was. `record_title` answering `None` rather than `""` for a connection is what
        stops an empty query matching a connection by accident.
        """
        store = _Store(
            entities=[_entity(n, f"component {n}") for n in range(4)],
            documents=[_document(1, "Something else entirely")],
        )

        assert _ranked(store, "", limit=12) == _expected_round_robin(store, "", 12)


def _expected_round_robin(store: _Store, query: str, limit: int) -> list[str]:
    """What the balanced ranking alone produces — computed by asking it, so this asserts *stability*
    rather than restating the algorithm."""
    from src.application.artifacts._ranking import rank_balanced
    from src.application.artifacts._search import search

    result = search(store, None, query, limit=limit)  # type: ignore[arg-type]
    return [h.record.artifact_id for h in rank_balanced(list(result.hits), limit, None)]


@pytest.mark.parametrize("limit", [1, 2, 5, 12, 20])
def test_an_exact_match_is_first_at_every_window_size(limit: int) -> None:
    store = _Store(
        entities=[_entity(n, f"sketching type {n}") for n in range(40)],
        notes=[_note(1, "Sketch before naming a type")],
    )

    assert _ranked(store, limit=limit)[0] == "SCR@1.pad#note/n1"
