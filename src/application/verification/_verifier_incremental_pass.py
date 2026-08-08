"""Running a pass that reuses a stored answer, and deciding when it cannot.

Separated from the verifier because it is a different kind of work. The verifier applies rules to a
file; this decides *which* files need the rules applied at all — comparing a stored snapshot against
the filesystem, widening the changed set to what it impacts, and falling back to a full pass when
the stored answer cannot be trusted.

Its collaborators arrive as one context rather than six parameters: a function needing six things
from its caller is a function whose context has not been named.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.verification._verifier_inventory import FileInventory, expand_impacted_paths
from src.application.verification._verifier_serde import merge_results, results_from_state
from src.application.verification.artifact_verifier_incremental import (
    STATE_SCHEMA_VERSION,
    IncrementalState,
    detect_changed_paths,
    requires_full_pass,
    serialize_result,
)
from src.application.verification.artifact_verifier_types import (
    VerificationResult,
    VerifierRuntimeConfig,
)
from src.application.verification.verifier_ports import FileInventoryPort, IncrementalStatePort


@dataclass(frozen=True)
class IncrementalPassContext:
    """What one incremental pass needs from the verifier that owns it."""

    inventory: FileInventoryPort
    incremental: IncrementalStatePort
    has_registry: bool
    verify_full: Callable[..., list[VerificationResult]]
    verify_subset: Callable[[FileInventory, set[str]], list[VerificationResult]]
    verify_documents: Callable[[Path], list[VerificationResult]]


def run_incremental_pass(
    ctx: IncrementalPassContext,
    repo_path: Path,
    *,
    include_diagrams: bool,
    cfg: VerifierRuntimeConfig,
) -> tuple[str, list[VerificationResult]]:
    """Verify, reusing the stored pass where it is still trustworthy, and say which pass answered."""
    inv = ctx.inventory.build(repo_path, include_diagrams=include_diagrams)
    state_path = ctx.incremental.state_path(repo_path, include_diagrams=include_diagrams)
    prev = ctx.incremental.load(state_path)
    head = ctx.incremental.git_head(repo_path)
    engine_sig = ctx.incremental.engine_signature()

    if requires_full_pass(
        prev, include_diagrams=include_diagrams, engine_sig=engine_sig, has_registry=ctx.has_registry
    ):
        mode = "full"
        results = ctx.verify_full(repo_path, include_diagrams=include_diagrams)
    else:
        assert prev is not None
        mode, results = _from_stored_state(
            ctx, prev, inv, repo_path=repo_path, include_diagrams=include_diagrams, cfg=cfg
        )

    # Documents live outside the incremental inventory, so the incremental modes must verify them
    # here — but every "full" result already includes them, and appending again reported each
    # document issue twice.
    if mode != "full":
        results.extend(ctx.verify_documents(repo_path))

    ctx.incremental.save(
        state_path,
        IncrementalState(
            schema_version=STATE_SCHEMA_VERSION,
            engine_signature=engine_sig,
            include_diagrams=include_diagrams,
            git_head=head,
            snapshots=inv.snapshots,
            results={inv.path_to_rel[r.path]: serialize_result(r) for r in results if r.path in inv.path_to_rel},
            include_registry=ctx.has_registry,
        ),
    )
    if cfg.log_mode:
        print(f"[ArtifactVerifier] mode={mode} include_diagrams={include_diagrams} files={len(results)}")
    return mode, results


def _from_stored_state(
    ctx: IncrementalPassContext,
    prev: IncrementalState,
    inv: FileInventory,
    *,
    repo_path: Path,
    include_diagrams: bool,
    cfg: VerifierRuntimeConfig,
) -> tuple[str, list[VerificationResult]]:
    changed, deleted = detect_changed_paths(inv, prev)
    if deleted:
        return "full", ctx.verify_full(repo_path, include_diagrams=include_diagrams)
    if not changed:
        cached = results_from_state(prev, inv)
        if cached is not None:
            return "incremental-cached", cached
        return "full", ctx.verify_full(repo_path, include_diagrams=include_diagrams)
    total = len(inv.ordered_paths)
    ratio = (len(changed) / total) if total > 0 else 1.0
    if ratio >= cfg.changed_ratio_threshold or len(changed) >= cfg.changed_count_threshold:
        return "full", ctx.verify_full(repo_path, include_diagrams=include_diagrams)
    return "incremental", merge_results(prev, inv, ctx.verify_subset(inv, expand_impacted_paths(inv, changed)))
