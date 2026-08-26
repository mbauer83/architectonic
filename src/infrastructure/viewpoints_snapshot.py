"""The viewpoint registry snapshot, as this process is configured.

`build_registry_snapshot` takes the three derivation budgets as arguments and defaults them, because
it lives in the application layer and the application layer does not read process configuration —
that boundary is deliberate and holds everywhere in `src/application/`. So every caller that wants
the *configured* budgets has had to name all three, and seven of them did, in seven copies of the same
five lines.

Two did not, and that is why this module exists rather than being a tidying-up. `_promote_viewpoints`
built its snapshot with the library defaults, so a repository whose settings raise the derivation hop
limit validated a promotion against a shorter reach than the promoted viewpoint would then use — and
nothing announced the difference. It now calls this. Seven copies of a call is a smell; one of them
silently disagreeing is the defect the smell was hiding.

`ArtifactVerifier` still uses the defaults, and that one is structural rather than an oversight: it
lives in `src/application/`, which may not read settings at all, so it cannot call this function. The
fix there is to inject the snapshot from the composition root that builds the verifier, which is a
change to its construction contract and not to a call site. Recorded here because the consequence is
real — the verifier can resolve a `derived.` path over a different reach than the REST surface
does — and because the next person to find it should find this note rather than the smell again.

One function, at the layer that may read settings.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot


def configured_registry_snapshot(
    catalogs: RuntimeCatalogs, repo_roots: Sequence[Path]
) -> RegistrySnapshot:
    """One snapshot, under this process's configured derivation budgets.

    Built once per caller and reused, as `build_registry_snapshot`'s own docstring asks: it scans every
    entity type's effective attribute schema across every repo tier, so per-file construction is what
    it warns against.
    """
    return build_registry_snapshot(
        catalogs,
        repo_roots,
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )
