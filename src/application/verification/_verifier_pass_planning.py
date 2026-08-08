"""Questions about a pass, answerable without running one.

A full pass re-verifies every file and takes minutes on a cold cache. Deciding whether to spend
that is only possible if the cost and its cause can be known first — cheaply, or the question costs
as much as the answer. Both functions here are cheap by construction: one compares four fields of
the stored state, the other is a stat sweep with no artifact read.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier_incremental import full_pass_reason, load_runtime_config
from src.application.verification.verifier_ports import FileInventoryPort, IncrementalStatePort


def pending_full_pass_reason(
    *,
    incremental: IncrementalStatePort,
    has_registry: bool,
    repo_path: Path,
    include_diagrams: bool,
) -> str | None:
    """Why the next pass would be a full one, or None if it would reuse the cache.

    None under ``ARCH_MODEL_VERIFY_MODE=full`` as well: configuration has already elected a full
    pass, so consent is not in question and a caller that cannot re-call is not blocked.
    """
    if load_runtime_config().mode != "incremental":
        return None
    state_path = incremental.state_path(repo_path, include_diagrams=include_diagrams)
    return full_pass_reason(
        incremental.load(state_path),
        include_diagrams=include_diagrams,
        engine_sig=incremental.engine_signature(),
        has_registry=has_registry,
    )


def count_verifiable_files(
    *, inventory: FileInventoryPort, repo_path: Path, include_diagrams: bool
) -> int:
    """How many files a pass would verify. A stat sweep, no artifact read."""
    return len(inventory.build(repo_path, include_diagrams=include_diagrams).ordered_paths)
