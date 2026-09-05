"""Turning passages into vectors, and the contract that lets everything above not care how.

`TextEncoder` is the seam the embedding decision promises: retrieval is expressed as a ranked list
of typed candidates and nothing above knows what produced the ranks, so changing encoder changes one
class. It is also what lets the retriever be exercised without 31 MB of weights on the machine
running the test.

Unit length belongs to the contract rather than to an implementation. It is what makes similarity a
dot product, and an encoder that returned unnormalised rows would put the decision about what
"similar" means in a second place — the caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@runtime_checkable
class TextEncoder(Protocol):
    """Encodes passages as unit vectors that compare by dot product."""

    def encode(self, passages: list[str]) -> NDArray[np.float32]: ...

    @property
    def dimensions(self) -> int: ...


class StaticEmbeddingEncoder:
    """A distilled token-to-vector lookup with pooling — no transformer forward pass.

    Chosen over a transformer encoder on measurement rather than preference: it encodes a query in
    0.04 ms against 10.5 ms, builds this corpus in 0.2 s against 15.5 s, and needs 108 MB less
    installed closure, while ranking no worse on the queries where either has headroom.

    Loading reads only local files. No query, artifact or fragment of either leaves the deployment,
    which is the disclosure boundary the decision draws, so construction takes a directory rather
    than a model name a library could resolve over the network.
    """

    def __init__(self, model_directory: Path) -> None:
        # Imported here rather than at module scope so a deployment with vector retrieval off pays
        # nothing for it: the import pulls tokenizers and safetensors and costs 0.13s measured.
        from model2vec import StaticModel  # noqa: PLC0415

        self._model = StaticModel.from_pretrained(str(model_directory))

    def encode(self, passages: list[str]) -> NDArray[np.float32]:
        if not passages:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        vectors = np.asarray(self._model.encode(passages), dtype=np.float32)
        return unit_rows(vectors)

    @property
    def dimensions(self) -> int:
        return int(self._model.dim)


def unit_rows(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    """Scale each row to unit length, leaving an all-zero row alone rather than dividing by zero.

    A passage of stop words the model has no vectors for encodes as zeros. That row should match
    nothing, which is what a zero row does under a dot product — dividing it would make it a NaN row
    instead, and NaN compares false against every threshold, which looks the same until it is sorted.
    """
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, lengths, out=np.zeros_like(vectors), where=lengths > 0)
