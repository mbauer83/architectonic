"""How closely a record's title matches what the reader typed — the tiers `rank_hits` orders by.

A query in a search box is usually being typed: its last word is unfinished, and the reader is spelling
the title of something they already know. Matching only whole terms made a title invisible to its own
prefix — `Artifact Ind` could not tell `Artifact Index` from any of the other artifacts that mention
the word *artifact*, so the title surfaced only once it was typed almost in full.

**Four tiers, strongest first, each a statement a reader can check by looking at the title:**

1. `EXACT` — the title *is* what was typed.
2. `PREFIX` — the title *begins with* what was typed, the last word possibly unfinished.
3. `WORD_PREFIXES` — every typed word *begins a word* of the title, in any order: `index artif`,
   or a word from the middle of the name.
4. `INFIX` — what was typed *appears inside* the title, as when the reader starts mid-word.

**Why tiers and not a score.** The tiers sit above per-kind scores that are on incomparable scales
(bm25, the token-match supplement, rank fusion), which is why `_ranking.py` round-robins across kinds
at all. A boolean statement about the title is the one thing every kind can be compared on.

**No synonyms, no stemming.** The scored path expands `diagram` to `view`; a tier does not, because
its value is that the sentence above it is literally true of the title. The widening from whole terms
to word prefixes is the one the typing reader needs, and it keeps that sentence true.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import IntEnum

from src.application.artifacts.scoring import tokenize

#: Fewer characters than this inside a word say nothing about which title was meant — `in` occurs in
#: half the titles there are. A prefix of the same length still counts: it is where the title starts.
_MIN_INFIX_CHARACTERS = 3


class TitleMatch(IntEnum):
    """The tiers, ordered so that a lower value is a closer match."""

    EXACT = 0
    PREFIX = 1
    WORD_PREFIXES = 2
    INFIX = 3


def normalised_terms(text: str) -> tuple[str, ...]:
    """A title or a query as comparable terms.

    Through `tokenize`, which the scored path already uses, so the two cannot disagree about what a
    word is. Casefolding and punctuation fall out of it: `"Sketch, before naming a TYPE!"` and
    `"sketch before naming a type"` normalise alike.
    """
    return tuple(tokenize(text.lower()))


def title_match(title_terms: Sequence[str] | None, query_terms: Sequence[str]) -> TitleMatch | None:
    """The closest tier this title reaches for this query, or `None` where it reaches none.

    `None` for a record with no title as well: a connection has none, and an empty query would
    otherwise "equal" an empty title and promote every connection in the corpus.
    """
    if not query_terms or not title_terms:
        return None
    title, query = " ".join(title_terms), " ".join(query_terms)
    if title == query:
        return TitleMatch.EXACT
    if title.startswith(query):
        return TitleMatch.PREFIX
    if all(any(word.startswith(term) for word in title_terms) for term in query_terms):
        return TitleMatch.WORD_PREFIXES
    if len(query) >= _MIN_INFIX_CHARACTERS and query in title:
        return TitleMatch.INFIX
    return None
