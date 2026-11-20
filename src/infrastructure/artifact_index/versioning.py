"""The read model's version, and the ETag a conditional read is allowed to promise from it.

An ETag is a promise: *the same tag means the same body*. The generation counter alone cannot make
that promise, because it starts again at zero in every process. A client holding the tag for
generation 7 from yesterday's process is told 304 by today's, whose generation 7 describes different
content — and a stale 304 is invisible, which is exactly what this product's own caching module
names as the failure to avoid.

It was not hypothetical. Recording a change against a promoted artifact left a running GUI showing
"enterprise-baseline" for that artifact indefinitely: the browser had the tag from before the
restart, the new process reached the same generation, and every revalidation answered 304 with the
old body. The artifact carried a change and said it did not.

So the tag carries this process's identity as well. The cost is one re-fetch per client after a
restart; the alternative is a promise the server cannot keep.
"""

from __future__ import annotations

import hashlib
import os
import time

from src.application.read_models import ReadModelVersion

__all__ = ["ReadModelVersion", "build_read_model_etag", "read_model_version_at"]

#: This process, distinctly enough that two of them never agree.
#:
#: The pid alone is not enough — they are reused, and a restart can land on one that has served a
#: different model. The start time makes the pair unique for any run a client's cache outlives.
_PROCESS_IDENTITY = f"{os.getpid()}:{time.time_ns()}"


def build_read_model_etag(scope_key: str, generation: int, *, beside: tuple[str, int] | None = None) -> str:
    """The tag for one generation of the model — and, with `beside`, of something that moves beside it.

    `beside` names a second counter and its value: what a read depends on that changes without the
    model changing. The model's generation stays in the tag, so such a tag moves whenever the model
    does and additionally on its own, and the name keeps two counters that happen to hold the same
    number from producing the same tag.
    """
    moment = f"{generation}" if beside is None else f"{generation}+{beside[0]}{beside[1]}"
    digest = hashlib.blake2b(
        f"{scope_key}:{_PROCESS_IDENTITY}:{moment}".encode("utf-8"),
        digest_size=10,
    ).hexdigest()
    return f'W/"model-{moment}-{digest}"'


def read_model_version_at(scope_key: str, generation: int, *, references: int, scratchpads: int) -> ReadModelVersion:
    """The version an index publishes: the model's tag, and one for each thing that moves beside it.

    `references` counts the changes that altered a "referenced in scratchpads" list without the
    model changing, and `scratchpads` every scratchpad change — see `ReadDependence` for which
    reads carry which, and why neither is folded into the model's own generation.
    """
    return ReadModelVersion(
        generation=generation,
        etag=build_read_model_etag(scope_key, generation),
        references_etag=build_read_model_etag(scope_key, generation, beside=("references", references)),
        scratchpads_etag=build_read_model_etag(scope_key, generation, beside=("scratchpads", scratchpads)),
    )
