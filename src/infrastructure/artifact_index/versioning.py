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

__all__ = ["ReadModelVersion", "build_read_model_etag"]

#: This process, distinctly enough that two of them never agree.
#:
#: The pid alone is not enough — they are reused, and a restart can land on one that has served a
#: different model. The start time makes the pair unique for any run a client's cache outlives.
_PROCESS_IDENTITY = f"{os.getpid()}:{time.time_ns()}"


def build_read_model_etag(scope_key: str, generation: int) -> str:
    digest = hashlib.blake2b(
        f"{scope_key}:{_PROCESS_IDENTITY}:{generation}".encode("utf-8"),
        digest_size=10,
    ).hexdigest()
    return f'W/"model-{generation}-{digest}"'
