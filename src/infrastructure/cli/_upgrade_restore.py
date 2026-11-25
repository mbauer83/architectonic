"""`arch-repair upgrade --list-checkpoints` and `--restore`: both act on the recorded sets, neither migrates.

A restore resolves the deployment the set was taken under when the command line names none, and
refuses while anything changed after the commit that took it — see `_upgrade_checkpoints`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from src.infrastructure.cli._upgrade_checkpoints import (
    checkpoint_base,
    databases_restored_whole,
    list_checkpoint_sets,
    load_checkpoint_set,
    restore_checkpoint_set,
    work_since_upgrade,
)
from src.infrastructure.cli._upgrade_deployment import DeploymentSide, build_deployment_side

#: The exit status of a restore refused to protect later work — the "blocked, nothing written" status
#: `arch-repair upgrade` uses for an unresolved migration.
EXIT_REFUSED = 3


def restore_or_list(
    args: argparse.Namespace,
    side: DeploymentSide,
    roots: list[Path],
    *,
    guard: Callable[[Path], None],
    rebuild_index: Callable[[Path], object],
) -> int:
    """`--list-checkpoints` and `--restore`: both act on the recorded sets, neither migrates."""
    base = checkpoint_base(
        workspace=args.workspace,
        settings_document=side.manifest.settings_document.path if side.manifest else None,
        roots=roots,
    )
    if args.list_checkpoints:
        sets = list_checkpoint_sets(base)
        if args.json_output:
            print(json.dumps([s.to_dict() for s in sets], indent=2))
        else:
            print(f"Checkpoint sets under {base}:" if sets else f"No checkpoint sets under {base}.")
            for s in sets:
                print(f"  {s.id}: {len(s.repositories)} repositor{'y' if len(s.repositories) == 1 else 'ies'}, "
                      f"{len(s.operational)} operational target(s)")
        return 0
    checkpoint_set = load_checkpoint_set(base, args.restore)
    if not side.active and checkpoint_set.operational and checkpoint_set.settings_document:
        # The set names the deployment it was taken under; its operational copies belong to that one.
        args.settings = checkpoint_set.settings_document
        side = build_deployment_side(args, os.environ)
    for repository in checkpoint_set.repositories:
        guard(Path(repository.root))
    later = work_since_upgrade(checkpoint_set)
    if later and not args.discard_later_work:
        print(
            f"NOT RESTORED — restoring checkpoint set {checkpoint_set.id} would discard work done since the "
            "upgrade:",
            file=sys.stderr,
        )
        for line in later:
            print(f"  {line}", file=sys.stderr)
        print(
            "Save or commit what you need elsewhere, then re-run with --discard-later-work to restore anyway.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    for database in databases_restored_whole(checkpoint_set):
        print(
            f"  {database}: put back as it was before the upgrade; anything recorded in it since is lost",
            file=sys.stderr,
        )
    done = restore_checkpoint_set(
        checkpoint_set, side.handles, rebuild_index=rebuild_index
    )
    if args.json_output:
        print(json.dumps({"restored": checkpoint_set.to_dict(), "actions": done}, indent=2))
    else:
        print(f"Restored checkpoint set {checkpoint_set.id}:")
        for line in done:
            print(f"  {line}")
    return 0
