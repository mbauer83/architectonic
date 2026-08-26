import math
import re

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
    ScratchpadRecord,
)
from src.domain.search_terms import expand_tokens


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def token_match_score(field_text: str, query_lc: str, tokens: list[str], weight: float) -> float:
    if not field_text:
        return 0.0
    field_lc = field_text.lower()
    score = weight if query_lc in field_lc else 0.0
    for token in tokens:
        if token in field_lc:
            score += weight * 0.5
    return score


def content_score(content: str, tokens: list[str], weight: float) -> float:
    if not content or not tokens:
        return 0.0
    content_lc = content.lower()
    word_count = max(len(content_lc.split()), 1)
    tf_sum = 0.0
    for token in tokens:
        count = content_lc.count(token)
        if count:
            tf = count / word_count
            tf_sum += weight * (1 + math.log(1 + tf))
    return tf_sum


def score_entity(rec: EntityRecord, query_lc: str, tokens: list[str]) -> float:
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.name, query_lc, expanded, 4.0)
    score += token_match_score(rec.display_label, query_lc, expanded, 3.5)
    score += token_match_score(rec.artifact_id, query_lc, expanded, 2.5)
    score += token_match_score(rec.display_alias, query_lc, expanded, 2.0)
    score += token_match_score(rec.artifact_type, query_lc, expanded, 2.0)
    score += token_match_score(rec.domain, query_lc, expanded, 1.5)
    score += token_match_score(rec.subdomain, query_lc, expanded, 1.5)
    score += content_score(rec.content_text, expanded, 1.0)
    for value in rec.extra.values():
        score += token_match_score(str(value), query_lc, expanded, 0.5)
    return score


def score_connection(rec: ConnectionRecord, query_lc: str, tokens: list[str]) -> float:
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.artifact_id, query_lc, expanded, 2.5)
    score += token_match_score(rec.conn_type, query_lc, expanded, 2.0)
    for entity_id in rec.source_ids + rec.target_ids:
        score += token_match_score(entity_id, query_lc, expanded, 1.5)
    score += content_score(rec.content_text, expanded, 1.0)
    return score


def score_diagram(rec: DiagramRecord, query_lc: str, tokens: list[str]) -> float:
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.name, query_lc, expanded, 4.0)
    score += token_match_score(rec.artifact_id, query_lc, expanded, 2.5)
    score += token_match_score(rec.diagram_type, query_lc, expanded, 2.0)
    return score


def score_document(rec: DocumentRecord, query_lc: str, tokens: list[str]) -> float:
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.title, query_lc, expanded, 4.0)
    score += token_match_score(rec.artifact_id, query_lc, expanded, 2.5)
    score += token_match_score(rec.doc_type, query_lc, expanded, 2.0)
    score += token_match_score(" ".join(rec.keywords), query_lc, expanded, 1.5)
    score += content_score(rec.content_text, expanded, 1.0)
    return score


def score_scratchpad_note(rec: ScratchpadNoteRecord, query_lc: str, tokens: list[str]) -> float:
    """Deliberately the lowest weights of any kind, and the shape says why.

    A note is a half-formed thought; an entity is a commitment. So a note's title carries the weight
    a document's *doc type* does rather than the weight of its title, its body counts half what a
    document's content does, and its address is not matched at all — a note id is minted from a
    clock and matching one would only ever be an accident.

    Its scratchpad's name is **not** matched, and that is the decision rather than an omission. A pad
    is a container; its notes are what search can return. So matching the container's name hands back
    notes whose own titles contain none of the query — ask for "Q3 platform thinking" and receive a
    note called "AI-Assisted and Agentic Development", which reads as a wrong answer however it was
    reached. Finding the *pad* is a different question, and one a note-shaped result cannot answer.

    This alone does not keep notes below model content: bm25 and the token-match supplement are on
    incomparable scales, so the guarantee lives in `_rank_balanced`, which draws the subordinate
    kinds last. The weights are what keeps a note from dominating *other notes* on a stray word.
    """
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.title, query_lc, expanded, 2.0)
    score += token_match_score(rec.element_type, query_lc, expanded, 1.0)
    score += token_match_score(rec.domain, query_lc, expanded, 1.0)
    score += content_score(rec.body, expanded, 0.5)
    return score


def score_scratchpad(rec: ScratchpadRecord, query_lc: str, tokens: list[str]) -> float:
    """A pad on its own words: the name someone chose, and the description they wrote.

    **Its notes' text is not matched, and that is the decision rather than an omission.** A note is
    not matched on its scratchpad's name for a reason recorded beside `score_scratchpad_note` — a pad
    is a container, so answering with its contents returns notes whose own titles contain none of the
    query. The mirror holds: handing back a *pad* because one of forty notes mentions a word reads as
    a wrong answer however it was reached, and that note is already returned in its own right.

    Weighted like a document, not like a note. A pad's name is something a person chose and typed, and
    its description is prose they wrote about what the pad is for — both are commitments about the
    container even where its contents are not. What keeps a pad below model content is
    `rank_balanced`, which draws subordinate kinds last; these weights only order pads against one
    another.
    """
    expanded = expand_tokens(tokens)
    score = 0.0
    score += token_match_score(rec.name, query_lc, expanded, 4.0)
    score += content_score(rec.description, expanded, 1.0)
    return score
