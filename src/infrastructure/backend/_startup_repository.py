"""Assembling the repository the backend serves, and refusing to serve a broken one.

Its own module because it is a different question from running a process. `arch_backend.py` parses
arguments, daemonises, binds a port and drains on a signal; what a served repository *is* — the
index over one or two roots, the transactions recovered before it is built, the registries repaired
before that, and the validations that abort rather than serve — is this.

The startup order is load-bearing and is stated in `initialise_repo`: recover durable transactions,
repair the group registry (which mutates files), build the index, scan for duplicates, then serve.
Group repair must precede the index build so the index is consistent with disk at the first served
request.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.infrastructure.backend._startup_id_checks import (
    assert_no_cross_repo_id_collisions,
    assert_no_duplicate_short_ids,
)
from src.infrastructure.search.provider import semantic_provider_for

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository

logger = logging.getLogger(__name__)


def initialise_repo(
    repo_root_path: Path, enterprise_root_path: Path | None, args: argparse.Namespace
) -> "ArtifactRepository":
    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.app_bootstrap import process_runtime_catalogs
    from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index
    from src.infrastructure.backend import startup_reconciliation
    from src.infrastructure.backend._group_registry_startup import repair_group_registries
    from src.infrastructure.backend._profile_registry_startup import validate_profile_registries
    from src.infrastructure.write.artifact_write.m4_transaction import recover_transactions

    roots = [p for p in (repo_root_path, enterprise_root_path) if p is not None]
    logger.info("Initializing backend — repo_root=%s enterprise_root=%s admin_mode=%s read_only=%s",
                repo_root_path, enterprise_root_path, args.admin_mode, args.read_only)
    index = (
        combined_artifact_index(repo_root_path, enterprise_root_path)
        if enterprise_root_path is not None
        else shared_artifact_index(repo_root_path)
    )
    # Startup ordering (WS9): recover durable transactions → repair group registry (mutates
    # files) → build index → duplicate scan → serve.  Group repair must precede the index
    # build so the index is consistent with disk at first served request (INV-2); the
    # duplicate scan fails closed on a genuine cross-mount collision (INV-1/WS2).
    for root in roots:
        recovered = recover_transactions(root, rebuild_index=index.refresh)
        if recovered:
            logger.warning("Recovered %s durable transaction(s) in %s", recovered, root)
    startup_reconciliation.settle_submissions_in_flight(enterprise_root_path)
    startup_reconciliation.forget_interrupted_worktrees(roots)
    repair_group_registries(repo_root_path, enterprise_root_path)
    # Class A profile-registry validation before the index build: a malformed registry or an
    # undefined binding makes the profile subsystem untrustworthy (engagement aborts,
    # enterprise warns) — mirrors the group-registry posture above (WU-Q1).
    validate_profile_registries(repo_root_path, enterprise_root_path)
    repo = ArtifactRepository(
        index,
        excluded_entity_types=process_runtime_catalogs().ontology.entity_types_with_class(
            "internal"
        ),
        semantic_provider=semantic_provider_for(index),
    )
    repo.refresh()
    startup_reconciliation.close_changes_already_integrated(repo)
    assert_no_duplicate_short_ids(index)
    assert_no_cross_repo_id_collisions(index)
    return repo


def run_startup_validations(repo: "ArtifactRepository") -> None:
    from src.application.startup_validation import (
        RepoCompatibilityError,
        SchemaPolicyError,
        validate_repo_compatibility,
        validate_schema_policy,
    )
    from src.infrastructure.app_bootstrap import build_module_registry, get_module_registry

    try:
        # Compare against the complete vocabulary (all modules, enabled or not) so that
        # artifacts belonging to a merely-disabled optional module (e.g. assurance diagrams
        # when no confidential store is configured) warn rather than abort startup.
        warnings = validate_repo_compatibility(
            repo,
            get_module_registry(),
            complete_registry=build_module_registry(complete_vocabulary=True),
        )
        for warning in warnings:
            logger.warning("Repository compatibility: %s", warning)
    except RepoCompatibilityError as exc:
        logger.error("Startup aborted — repository uses types not in the module registry:\n%s", exc)
        sys.exit(1)

    try:
        for warning in validate_schema_policy(repo):
            logger.warning("Schema policy: %s", warning)
    except SchemaPolicyError as exc:
        logger.error("Startup aborted — attribute-schema policy violations:\n%s", exc)
        sys.exit(1)
