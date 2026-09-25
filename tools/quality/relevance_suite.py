"""A labelled query suite over the model, so a claim about search quality can be false.

Search quality was previously asserted by reading result lists and finding them reasonable. That
cannot distinguish a change that helps from one that does nothing, and it certainly cannot catch one
that helps a hard query while quietly costing an easy one. This scores recall against queries whose
answers are known.

**Four strata, each with one intended answer per query.**

- `name` — an element's own name as the query, itself as the answer. The easiest question there is,
  and the one a reader asks most. Its purpose is the floor: nothing may regress here.
- `summary` — an element's own opening prose as the query, itself as the answer. Still lexical
  overlap, still nearly always answerable by matching terms.
- `paraphrase` — a description of an element written without its name or its own wording
  (`paraphrase_queries.py`), the element as the answer. This is the question retrieval by meaning
  exists for: someone knows what a thing does or is for, not what it is called.
- `described` — a sentence in one of the repository's documents that links to exactly one element,
  with that link taken out, the element as the answer. A person wrote it about the element in words
  of their own; it sometimes cites the element rather than describing it, so it is reported beside
  the paraphrases rather than instead of them.

**Derived at read time where the repository states the answer.** `name`, `summary` and `described`
come from whatever the repository holds, so a rename changes the query with the artifact. The
paraphrases are written, and so committed, but keyed by rename-stable ids.

**It reports rates; it does not decide what rate is acceptable.** A caller compares two
configurations over one sample. Comparing a rate against a remembered number would be comparing
today's corpus against yesterday's, which is not a fact about search.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.application.document_links import is_external_or_anchor_href, iter_markdown_links, strip_anchor
from src.domain.artifact_id import stable_id
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from tools.quality.paraphrase_queries import PARAPHRASES

#: How many of each derived stratum to draw. Enough that a few queries either way do not move the
#: rate, small enough that four strata against two configurations stay a few seconds.
STRATUM_SIZE = 120

#: The window recall is measured at — what a reader actually sees before scrolling.
RECALL_AT = 10

#: Characters of an artifact's prose taken as the `summary` stratum's query. About a sentence: long
#: enough to be a question, short enough that it is a summary rather than the whole record.
_SUMMARY_CHARACTERS = 110

#: A `described` query shorter than this, once its link is out, says too little to be a question.
_MIN_DESCRIBED_WORDS = 8

#: Where one sentence of document prose ends: a full stop before a capital or a link, a blank line,
#: or the start of a list item, table row or heading.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z*`\[])|\n\s*\n|\n(?=\s*[-|#])")

#: Markdown emphasis, code, table and heading marks, which say nothing a query would.
_MARKUP = re.compile(r"[*`#|>]")


class LabelledCorpus(Protocol):
    """The questions drawing a suite asks of a repository, and no more.

    Narrower than `ReadableArtifactStore` deliberately, the way `ports.py` invites: a suite that
    demanded the whole store could only ever be exercised against a real index, and the point of
    the instrument is that its own derivation is checkable.
    """

    def entity_ids(self) -> set[str]: ...
    def get_entity(self, artifact_id: str) -> EntityRecord | None: ...
    def list_documents(self) -> list[DocumentRecord]: ...


@dataclass(frozen=True, slots=True)
class LabelledQuery:
    """A query and the one artifact it is meant to find."""

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


def draw_strata(
    store: LabelledCorpus, paraphrases: Sequence[tuple[str, str]] = PARAPHRASES
) -> dict[str, list[LabelledQuery]]:
    """The four strata, each drawn deterministically so two runs over one corpus agree."""
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
        "paraphrase": _paraphrase_queries(entities, paraphrases),
        "described": _stride(_described_queries(store, entities)),
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


def _paraphrase_queries(
    entities: Sequence[EntityRecord], paraphrases: Sequence[tuple[str, str]]
) -> list[LabelledQuery]:
    """Each written paraphrase whose element still exists, answered by that element's current id."""
    by_stable = {stable_id(entity.artifact_id): entity for entity in entities}
    return [
        LabelledQuery(query, by_stable[key].artifact_id)
        for key, query in paraphrases
        if key in by_stable
    ]


def _described_queries(store: LabelledCorpus, entities: Sequence[EntityRecord]) -> list[LabelledQuery]:
    """Document sentences that link to exactly one entity, the link taken out, that entity the answer."""
    by_path = {entity.path.resolve(): entity for entity in entities}
    drawn: list[LabelledQuery] = []
    for document in sorted(store.list_documents(), key=lambda d: d.artifact_id):
        for sentence in _sentences(document.content_text):
            labelled = _described(sentence, document.path.parent, by_path)
            if labelled is not None:
                drawn.append(labelled)
    return drawn


def _sentences(text: str) -> Iterable[str]:
    start = 0
    for boundary in _SENTENCE_END.finditer(text):
        yield text[start : boundary.start()]
        start = boundary.end()
    yield text[start:]


def _described(sentence: str, directory: Path, by_path: dict[Path, EntityRecord]) -> LabelledQuery | None:
    """The sentence as a query for the one entity it links to, or None where it links to none or several.

    The answer's link is removed, label and all, so the query does not name what it asks for; any
    other link keeps its label, which is part of what the sentence says.
    """
    links = iter_markdown_links(sentence)
    linked = [
        (link, entity)
        for link in links
        if not is_external_or_anchor_href(link.href)
        and (entity := by_path.get((directory / strip_anchor(link.href)).resolve())) is not None
    ]
    if len(linked) != 1:
        return None
    answer_link, entity = linked[0]
    text = sentence
    for link in links:
        text = text.replace(f"[{link.label}]({link.href})", "" if link is answer_link else link.label)
    query = " ".join(_MARKUP.sub(" ", text).split())
    return LabelledQuery(query, entity.artifact_id) if len(query.split()) >= _MIN_DESCRIBED_WORDS else None
