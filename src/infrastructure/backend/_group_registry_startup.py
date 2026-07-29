"""Startup-time group-registry repair for the backend composition root."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def repair_group_registries(repo_root_path: Path, enterprise_root_path: Path | None) -> None:
    """Repair the engagement group registry (and validate the enterprise one) under the gate.

    Runs before the index build so any file mutation is reflected by the first index load.
    """
    from src.application.group_registry_validation import GroupRegistryError, validate_and_repair_group_registry
    from src.infrastructure.app_bootstrap import get_module_registry, registered_meta_ontology_values
    from src.infrastructure.workspace.mutation_gate import get_workspace_gate

    valid_meta_ontologies = registered_meta_ontology_values(get_module_registry())
    with get_workspace_gate().privileged_writing():
        try:
            for msg in validate_and_repair_group_registry(
                repo_root_path,
                valid_meta_ontologies=valid_meta_ontologies,
            ):
                logger.info("Group registry repair: %s", msg)
        except (GroupRegistryError, OSError) as exc:
            logger.error("Startup aborted — group registry error:\n%s\nFix .arch-repo/groups.yaml and restart.", exc)
            sys.exit(1)

        if enterprise_root_path is not None:
            try:
                for msg in validate_and_repair_group_registry(
                    enterprise_root_path,
                    valid_meta_ontologies=valid_meta_ontologies,
                    read_only=True,
                ):
                    logger.warning("Group registry (enterprise): %s", msg)
            except GroupRegistryError as exc:
                logger.warning("Enterprise group registry has errors (server will start; fix when possible):\n%s", exc)
