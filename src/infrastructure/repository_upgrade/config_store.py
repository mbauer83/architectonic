"""`.arch-repo/config.yaml` read/write for the repository-upgrade stamp: format_contract_version + applied steps.

Reuses `load_repo_config` (the same file `_startup_schema_policy` reads for
`required_defaults_policy`) so both consumers agree on one loader; writing merges into the
existing dict rather than replacing it, so unrelated keys survive.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application._startup_schema_policy import load_repo_config
from src.infrastructure.atomic_file import write_atomic

FORMAT_CONTRACT_VERSION_KEY = "format_contract_version"
APPLIED_UPGRADE_STEPS_KEY = "applied_upgrade_steps"
_ARCH_REPO_DIR = ".arch-repo"
_CONFIG_FILE = _ARCH_REPO_DIR + "/config.yaml"


def read_applied_steps(repo_root: Path) -> frozenset[str]:
    config = load_repo_config(repo_root)
    raw = config.get(APPLIED_UPGRADE_STEPS_KEY, [])
    return frozenset(str(v) for v in raw) if isinstance(raw, list) else frozenset()


def read_format_contract_version(repo_root: Path) -> str | None:
    config = load_repo_config(repo_root)
    raw = config.get(FORMAT_CONTRACT_VERSION_KEY)
    return str(raw) if raw is not None else None


def stamp_repo(
    repo_root: Path,
    *,
    format_contract_version: str,
    applied_step_ids: frozenset[str],
) -> None:
    config_path = repo_root / _CONFIG_FILE
    config = load_repo_config(repo_root)
    config[FORMAT_CONTRACT_VERSION_KEY] = format_contract_version
    config[APPLIED_UPGRADE_STEPS_KEY] = sorted(applied_step_ids)
    write_atomic(config_path, str(yaml.safe_dump(config, default_flow_style=False, sort_keys=True)))
