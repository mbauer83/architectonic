"""Unit length is the encoder's contract, not an implementation detail.

It is what makes similarity a dot product. An encoder that returned unnormalised rows would move
the decision about what "similar" means into the retriever, and a NaN row — what dividing a
zero-length vector produces — compares false against every threshold, which looks exactly like a
passage that simply did not match until it reaches a sort.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.infrastructure.bootstrap.embedding_model_asset import integrity_failures, model_directory
from src.infrastructure.search.text_encoder import StaticEmbeddingEncoder, TextEncoder, unit_rows


def test_rows_come_back_at_unit_length() -> None:
    scaled = unit_rows(np.array([[3.0, 4.0], [1.0, 0.0]], dtype=np.float32))
    assert np.allclose(np.linalg.norm(scaled, axis=1), 1.0)


def test_direction_is_preserved() -> None:
    scaled = unit_rows(np.array([[3.0, 4.0]], dtype=np.float32))
    assert np.allclose(scaled, [[0.6, 0.8]])


def test_an_all_zero_row_stays_zero_rather_than_becoming_nan() -> None:
    scaled = unit_rows(np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32))
    assert not np.isnan(scaled).any()
    assert np.allclose(scaled[0], 0.0)


def test_a_zero_row_matches_nothing_under_a_dot_product() -> None:
    """Which is the behaviour a passage of words the model has no vectors for should have."""
    zero = unit_rows(np.array([[0.0, 0.0]], dtype=np.float32))
    assert float((zero @ np.array([0.6, 0.8], dtype=np.float32))[0]) == 0.0


def test_no_rows_is_not_an_error() -> None:
    assert unit_rows(np.zeros((0, 4), dtype=np.float32)).shape == (0, 4)


# ── the real encoder, when this machine has the weights ──────────────────────

_asset_failures = integrity_failures()
_needs_weights = pytest.mark.skipif(
    bool(_asset_failures),
    reason=f"embedding weights not installed here — run get-embedding-model ({'; '.join(_asset_failures)})",
)


@_needs_weights
def test_the_static_encoder_satisfies_the_contract_it_is_injected_as() -> None:
    encoder = StaticEmbeddingEncoder(model_directory())
    assert isinstance(encoder, TextEncoder)
    assert encoder.dimensions > 0


@_needs_weights
def test_the_static_encoder_returns_one_unit_row_per_passage() -> None:
    encoder = StaticEmbeddingEncoder(model_directory())
    vectors = encoder.encode(["promotion across tiers", "a wholly unrelated sentence"])
    assert vectors.shape == (2, encoder.dimensions)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


@_needs_weights
def test_the_static_encoder_answers_an_empty_batch_with_no_rows() -> None:
    """Building an empty corpus must not need a special case in the caller."""
    encoder = StaticEmbeddingEncoder(model_directory())
    assert encoder.encode([]).shape == (0, encoder.dimensions)


@_needs_weights
def test_related_wording_scores_above_unrelated_wording() -> None:
    """The whole reason this branch exists: a query that shares no words with its answer."""
    encoder = StaticEmbeddingEncoder(model_directory())
    query, related, unrelated = encoder.encode(
        [
            "combining several rankings into one",
            "Reciprocal rank fusion merges ranked lists by position.",
            "The kettle boils water for tea.",
        ]
    )
    assert float(query @ related) > float(query @ unrelated)
