"""A labelled query suite derived from the model, so a claim about search quality can be false.

Search quality was previously asserted by reading result lists and finding them reasonable. That
cannot distinguish a change that helps from one that does nothing, and it certainly cannot catch one
that helps a hard query while quietly costing an easy one. This derives ground truth the repository
already contains and scores recall against it.

**Three strata, each labelled by something the model states rather than by an opinion.**

- `name` — an artifact's own name as the query, itself as the answer. The easiest question there is,
  and the one a reader asks most. Its purpose is the floor: nothing may regress here.
- `summary` — an artifact's own opening prose as the query, itself as the answer. Still lexical
  overlap, still nearly always answerable by matching terms.
- `realises` — a requirement's own wording as the query, the component that realises it as the
  answer, with the component's name removed from the query so the two share no name. This is the
  stratum with headroom: the words a requirement uses are not the words its realising component is
  called, which is exactly the question term matching cannot answer.

**Derived at read time, never committed as a snapshot.** A file of query/answer pairs goes stale the
moment an artifact is renamed, and then fails for a reason that has nothing to do with search. What
is committed is the derivation, so the suite is always about the repository as it currently stands.

**It reports rates; it does not decide what rate is acceptable.** A caller compares two
configurations over one sample. Comparing a rate against a remembered number would be comparing
today's corpus against yesterday's, which is not a fact about search.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

#: How many of each stratum to draw. Enough that a few queries either way do not move the rate,
#: small enough that three strata against two configurations stay a few seconds.
STRATUM_SIZE = 120

#: The window recall is measured at — what a reader actually sees before scrolling.
RECALL_AT = 10

#: Characters of an artifact's prose taken as the `summary` stratum's query. About a sentence: long
#: enough to be a question, short enough that it is a summary rather than the whole record.
_SUMMARY_CHARACTERS = 110

#: The relation that labels the `realises` stratum. The model carries several hundred, each one a
#: statement that this component is what answers this requirement.
_REALISATION = "archimate-realization"


class LabelledCorpus(Protocol):
    """The three questions drawing a suite asks of a repository, and no more.

    Narrower than `ReadableArtifactStore` deliberately, the way `ports.py` invites: a suite that
    demanded the whole store could only ever be exercised against a real index, and the point of
    the instrument is that its own derivation is checkable.
    """

    def entity_ids(self) -> set[str]: ...
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...
    def list_connections_by_types(self, types: frozenset[str]) -> list[ConnectionRecord]: ...


@dataclass(frozen=True, slots=True)
class LabelledQuery:
    """A query and the one artifact the model says answers it."""

    query: str
    gold_artifact_id: str


@dataclass(frozen=True, slots=True)
class StratumResult:
    """How a configuration did on one stratum."""

    name: str
    answered: int
    asked: int

    @property
    def recall(self) -> float:
        return self.answered / self.asked if self.asked else 0.0


#: Answers a query with ranked artifact ids, best first. Both configurations under comparison are
#: passed as one of these, so the suite never knows which retrievers either of them runs.
RankedSearch = Callable[[str], Sequence[str]]


def draw_strata(store: LabelledCorpus) -> dict[str, list[LabelledQuery]]:
    """The three strata, each drawn deterministically so two runs over one corpus agree."""
    entities = _entities(store)
    return {
        "name": _stride([LabelledQuery(e.name, e.artifact_id) for e in entities if e.name]),
        "summary": _stride(
            [
                LabelledQuery(summary, e.artifact_id)
                for e in entities
                if (summary := _opening_prose(e.content_text))
            ]
        ),
        "realises": _stride(_realisation_queries(store, entities)),
    }


def score(searching: RankedSearch, stratum: Sequence[LabelledQuery], name: str) -> StratumResult:
    """Recall@`RECALL_AT`: how often the gold answer is in the window a reader sees."""
    answered = sum(
        1 for labelled in stratum if labelled.gold_artifact_id in searching(labelled.query)[:RECALL_AT]
    )
    return StratumResult(name=name, answered=answered, asked=len(stratum))


def _entities(store: LabelledCorpus) -> list[EntityRecord]:
    """Every entity, by id, in a stable order — the order the stride below samples."""
    found = (store.get_entity(artifact_id) for artifact_id in sorted(store.entity_ids()))
    return [record for record in found if record is not None]


def _stride(candidates: Sequence[LabelledQuery]) -> list[LabelledQuery]:
    """`STRATUM_SIZE` drawn evenly across `candidates`, deterministically.

    A stride rather than a random sample with a seed: a seed makes the draw reproducible only for
    whoever remembers it, while a stride over a sorted list is reproducible by anyone who runs this,
    and it spreads the draw across the corpus instead of clustering it at one end.
    """
    if len(candidates) <= STRATUM_SIZE:
        return list(candidates)
    step = len(candidates) / STRATUM_SIZE
    return [candidates[int(index * step)] for index in range(STRATUM_SIZE)]


def _opening_prose(content: str) -> str:
    """The first `_SUMMARY_CHARACTERS` of a record's prose, with its heading dropped.

    The heading repeats the name, and a query that contains the name is the `name` stratum wearing a
    disguise — it would make this stratum look easier than it is.
    """
    body = " ".join(line for line in content.splitlines() if not line.strip().startswith("#"))
    collapsed = " ".join(body.split())
    return collapsed[:_SUMMARY_CHARACTERS].strip()


def _realisation_queries(
    store: LabelledCorpus, entities: Sequence[EntityRecord]
) -> list[LabelledQuery]:
    """A requirement's wording asking for the component that realises it.

    The component's own name is removed from the query, so what is left shares no name with the
    answer and matching terms cannot find it by accident. That removal is the whole reason this
    stratum measures anything the other two do not.
    """
    by_id = {entity.artifact_id: entity for entity in entities}
    drawn: list[LabelledQuery] = []
    for connection in store.list_connections_by_types(frozenset({_REALISATION})):
        realiser = _single(connection.source_ids, by_id)
        realised = _single(connection.target_ids, by_id)
        if realiser is None or realised is None:
            continue
        wording = _without_words_of(
            f"{realised.name}. {_opening_prose(realised.content_text)}",
            realiser.name,
        )
        if wording:
            drawn.append(LabelledQuery(wording, realiser.artifact_id))
    return sorted(drawn, key=lambda labelled: labelled.gold_artifact_id)


def _single(ids: Iterable[str], by_id: dict[str, EntityRecord]) -> EntityRecord | None:
    """The one entity an endpoint names, or None where it names none or more than one."""
    found = [by_id[artifact_id] for artifact_id in ids if artifact_id in by_id]
    return found[0] if len(found) == 1 else None


def _without_words_of(text: str, removed: str) -> str:
    """`text` with every word of `removed` taken out, case-insensitively."""
    excluded = {word.lower().strip(".,:;()") for word in removed.split() if word}
    kept = [word for word in text.split() if word.lower().strip(".,:;()") not in excluded]
    return " ".join(kept).strip()
