"""The prose a record is embedded as, and how a long one becomes several vectors.

Keyword search reads a record field by field, weighting a name above a body. An encoder cannot: it
turns one passage into one vector, so something has to decide what passage a record *is*. That
decision lives here, once, because a second answer to it would silently index a different corpus
from the one any measurement was taken over — and nothing would fail, the results would just be
worse for a reason no test could name.

What a record contributes is what a reader would recognise it by: its title, what kind of thing it
is, and its own words. Identifiers are left out on purpose. `FNC@1788599685.KQCmD1g` carries no
meaning to a model trained on English, and including it would put a token in every passage that
resembles every other passage's — exactly the noise mean-pooling is worst at ignoring. Keyword
search already answers an id perfectly, and this branch exists for the query keyword search cannot
answer.
"""

from __future__ import annotations

from src.domain.ontology_representation.artifact_types import (
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
)

#: A record kind that carries enough prose to be worth a vector.
CorpusRecord = EntityRecord | DocumentRecord | DiagramRecord

#: Characters per chunk. Static embeddings mean-pool a passage, so a long one dilutes towards the
#: average of everything in it; splitting keeps a passage about one thing. The relevance
#: measurement this branch was accepted on was taken at this size.
CHUNK_CHARACTERS = 512


def embeddable_text(record: CorpusRecord) -> str:
    """The single passage this record is encoded as, before chunking."""
    match record:
        case EntityRecord():
            return _joined(record.name, record.artifact_type, " ".join(record.keywords), record.content_text)
        case DocumentRecord():
            return _joined(record.title, record.doc_type, " ".join(record.keywords), record.content_text)
        case DiagramRecord():
            return _joined(record.name, record.diagram_type)


def text_chunks(text: str, *, size: int = CHUNK_CHARACTERS) -> tuple[str, ...]:
    """`text` split into passages of about `size` characters, never mid-word.

    A record shorter than one chunk yields one chunk, which is the common case; an empty record
    yields none, so nothing indexes a vector for a passage with no words in it. A single word longer
    than `size` — a URL, a base64 blob — overruns rather than being cut, because half a token
    encodes as something the whole one does not resemble.
    """
    words = text.split()
    if not words:
        return ()
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        addition = len(word) + (1 if current else 0)
        if current and length + addition > size:
            chunks.append(" ".join(current))
            current, length = [word], len(word)
        else:
            current.append(word)
            length += addition
    chunks.append(" ".join(current))
    return tuple(chunks)


def _joined(*parts: str) -> str:
    """The parts that carry words, in order, separated so they read as one passage."""
    return ". ".join(part.strip() for part in parts if part and part.strip())
