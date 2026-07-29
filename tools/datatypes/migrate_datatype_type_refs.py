#!/usr/bin/env python3
"""Migrate legacy datatype attribute strings to canonical tagged references.

Dry-run is the default and emits JSON. ``--apply`` is unavailable while any
reference is ambiguous. An optional mapping file resolves a per-attribute key:

    {"DIAGRAM:OWNER:ATTRIBUTE":
        {"kind": "classifier", "selector": "TARGET_DIAGRAM:TARGET_LEGACY_ID"}}

Canonical classifier ``id`` and primitive ``name`` targets are also supported.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from tools.datatypes._datatype_type_migration import (
    MigrationBlockedError,
    MigrationPlan,
    _parse,
    apply_migration,
    plan_migration,
)

__all__ = [
    "MigrationBlockedError",
    "MigrationPlan",
    "_parse",
    "apply_migration",
    "plan_migration",
]


def _load_mappings(path: Path | None) -> Mapping[str, object]:
    if path is None:
        return {}
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Mapping file must contain a JSON object")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_roots", nargs="+", type=Path)
    parser.add_argument("--mapping-file", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = plan_migration(args.repo_roots, mappings=_load_mappings(args.mapping_file))
    report_text = json.dumps(plan.report, indent=2, sort_keys=True)
    if args.report:
        args.report.write_text(report_text + "\n", encoding="utf-8")
    print(report_text)
    if not args.apply:
        return
    try:
        changed = apply_migration(plan)
    except MigrationBlockedError as error:
        sys.exit(f"ERROR: {error}")
    print(json.dumps({"applied": True, "changed_paths": [str(path) for path in changed]}))


if __name__ == "__main__":
    main()
