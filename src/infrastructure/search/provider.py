"""Whether this process retrieves by meaning, and what it says when it cannot.

Three conditions have to hold: the deployment asked for it, the weights are installed and intact,
and the model loads. Any of them failing leaves search exactly as it is without the branch — which
is the whole of what the product promises — so none of them raises. Each says once, at the level a
reader of the log will look for it, which condition it was.

Silence would be the wrong answer to all three. An operator who turned the setting on and got no
change has to be able to find out that the asset is missing without reading this file.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from src.application.ports import ReadableArtifactStore
from src.config.storage_settings import storage_read_model_semantic_search
from src.infrastructure.bootstrap.embedding_model_asset import integrity_failures, model_directory
from src.infrastructure.search.text_encoder import StaticEmbeddingEncoder, TextEncoder
from src.infrastructure.search.vector_retriever import VectorRetriever

logger = logging.getLogger(__name__)


def semantic_provider_for(store: ReadableArtifactStore) -> VectorRetriever | None:
    """A retriever over `store`, or None when this deployment does not have the branch.

    Building it reads every record and encodes the corpus. That is 0.05s measured, which is why it
    happens here at construction rather than behind a lazily-built cache with a staleness question.
    """
    encoder = _process_encoder()
    if encoder is None:
        return None
    retriever = VectorRetriever(store, encoder)
    logger.info("semantic search enabled: %d passages encoded", retriever.corpus_size)
    return retriever


@lru_cache(maxsize=1)
def _process_encoder() -> TextEncoder | None:
    """The one encoder this process uses, or None with the reason logged.

    Cached per process because the weights are the same for every store a process serves and loading
    them costs 0.35s: a backend serving two repository roots should read 30 MB once. The cache is on
    the encoder and not on the retriever — the matrix is per corpus, and sharing one across stores is
    how a query gets answered from a neighbouring checkout's model.
    """
    if not storage_read_model_semantic_search():
        return None
    failures = integrity_failures()
    if failures:
        logger.warning(
            "semantic search is enabled but the embedding model is not usable, so search will answer "
            "by keyword alone — run get-embedding-model. %s",
            "; ".join(failures),
        )
        return None
    try:
        return StaticEmbeddingEncoder(model_directory())
    except Exception as exc:  # noqa: BLE001 — any load failure degrades to keyword search
        logger.warning(
            "semantic search is enabled but the embedding model failed to load, so search will "
            "answer by keyword alone: %s",
            exc,
        )
        return None
