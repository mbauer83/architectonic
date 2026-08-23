"""`arch-assurance seed` — load a demo/bootstrap assurance bundle, optionally
with live security signals.

The model load reuses ``import_store`` (the same path as `arch-assurance import`)
rather than reimplementing a second bundle reader — seeding IS an import with a
conventional default input and replace-by-default semantics, so a re-seed is
idempotent instead of accumulating duplicates.

Signal anchors are declared BY THE BUNDLE, in an optional top-level
``signal_anchors`` list, never hardcoded here: anchor ids identify entities in one
specific architecture repository, so a shipped constant would be meaningless in
any other workspace. Each entry names the anchor and the SBOM target to generate
for it.

That coupling is also why the bundle lives IN the repository it describes —
``.arch-repo/assurance-seed.json``, beside the other per-repository declarations — and
is resolved from the active engagement root rather than from the working directory. A
cwd-relative default only worked when the command was run from one particular place,
and gave a second engagement nowhere to put its own seed.

``signal_anchors`` is AUTHORED seed metadata, not store state: the store never
holds it and ``import`` ignores it. ``arch-assurance export`` does not *produce*
it either, but it does carry it over from an existing target bundle
(``lifecycle._AUTHORED_BUNDLE_KEYS``), so regenerating a seed by exporting a live
store over the old one preserves the block. Exporting to a fresh path does not,
and there the anchors have to be re-added by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

DEFAULT_SEED_FILENAME = "assurance-seed.json"
SEED_REPO_SUBDIR = ".arch-repo"


@dataclass(frozen=True)
class SignalAnchor:
    """One anchor the bundle wants live signals for."""

    anchor_entity_id: str
    target: str
    label: str = ""


def parse_signal_anchors(bundle: Any) -> list[SignalAnchor]:
    """Read the bundle's optional ``signal_anchors`` block.

    A malformed entry is an error rather than a skip: silently ingesting for a
    subset would look identical to a clean run while leaving anchors with no
    snapshot at all.
    """
    raw = bundle.get("signal_anchors") if isinstance(bundle, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("signal_anchors must be a list of {anchor_entity_id, target} objects")
    anchors: list[SignalAnchor] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"signal_anchors[{index}] must be an object")
        anchor_id = str(entry.get("anchor_entity_id") or "").strip()
        target = str(entry.get("target") or "").strip()
        if not anchor_id:
            raise ValueError(f"signal_anchors[{index}] is missing anchor_entity_id")
        if not target:
            raise ValueError(f"signal_anchors[{index}] ({anchor_id}) is missing target")
        anchors.append(SignalAnchor(
            anchor_entity_id=anchor_id, target=target, label=str(entry.get("label") or ""),
        ))
    return anchors


def _engagement_root() -> Path | None:
    from src.config.workspace_paths import resolve_workspace_repo_roots  # noqa: PLC0415

    roots = resolve_workspace_repo_roots()
    return roots[0] if roots else None


def _resolve_seed_path(args: argparse.Namespace) -> Path:
    """``--input`` wins; otherwise the active engagement repository's own seed.

    Raises rather than falling back to the working directory: which bundle to load is a
    question about which repository is active, and guessing it from cwd is how the command
    came to work from exactly one place.
    """
    if getattr(args, "input", None):
        return Path(args.input)
    root = _engagement_root()
    if root is None:
        raise RuntimeError(
            "no engagement repository resolved — run `arch-init`, or pass the bundle "
            "explicitly with --input"
        )
    return root / SEED_REPO_SUBDIR / DEFAULT_SEED_FILENAME


def _ingest_signals(
    anchors: Sequence[SignalAnchor], *, repo_root: Path, osv_base_url: str | None,
) -> int:
    from src.application.security_signals.command import IngestActivated  # noqa: PLC0415
    from src.infrastructure.assurance.signal_sources import (  # noqa: PLC0415
        SBOM_TARGETS,
        ingest_live_target,
    )
    from src.infrastructure.assurance.store_factory import get_assurance_bundle  # noqa: PLC0415
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    unknown = sorted({a.target for a in anchors} - set(SBOM_TARGETS))
    if unknown:
        print(f"Error: unknown SBOM target(s) {', '.join(unknown)}; "
              f"supported: {', '.join(sorted(SBOM_TARGETS))}", file=sys.stderr)
        return 1

    manifest = resolve_manifest()
    assurance = get_assurance_bundle(
        repo_root,
        db_path=manifest.assurance_db_path.path,
        signals_db_path=manifest.signals_db_path.path,
    )
    snapshot_store = assurance.snapshot_store
    if snapshot_store is None:
        print("Error: --with-signals requires the SQLCipher store with co-located signals",
              file=sys.stderr)
        return 1

    failures = 0
    for anchor in anchors:
        name = anchor.label or anchor.anchor_entity_id
        print(f"Ingesting {anchor.target} signals for {name} ...")
        try:
            result = ingest_live_target(
                anchor.target, anchor.anchor_entity_id,
                snapshot_store=snapshot_store, repo_root=repo_root,
                osv_base_url=osv_base_url,
            )
        except Exception as exc:  # noqa: BLE001 — one anchor's failure must not hide the rest
            print(f"  failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue
        if isinstance(result, IngestActivated):
            print(f"  snapshot {result.snapshot_id}: "
                  f"{result.persisted_component_count} components, "
                  f"{result.persisted_finding_count} findings"
                  + (f" ({result.collapsed_finding_count} collapsed by alias)"
                     if result.collapsed_finding_count else ""))
        else:
            print(f"  {type(result).__name__}: {result}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def cmd_seed(args: argparse.Namespace) -> int:
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore  # noqa: PLC0415
    from src.infrastructure.assurance.lifecycle import import_store  # noqa: PLC0415
    from src.infrastructure.cli._assurance_commands import _default_db_path  # noqa: PLC0415

    try:
        seed_path = _resolve_seed_path(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not seed_path.is_file():
        print(f"Error: seed bundle not found: {seed_path}", file=sys.stderr)
        return 1
    try:
        bundle = json.loads(seed_path.read_text())
        anchors = parse_signal_anchors(bundle)
    except (ValueError, OSError) as exc:
        print(f"Error: cannot read {seed_path}: {exc}", file=sys.stderr)
        return 1

    # Fail BEFORE mutating anything: a --with-signals run against a bundle that
    # declares no anchors would otherwise import the model and report success
    # while silently ingesting nothing.
    if args.with_signals and not anchors:
        print(f"Error: --with-signals requires a 'signal_anchors' list in {seed_path}",
              file=sys.stderr)
        return 1

    db_path = Path(args.db_path) if args.db_path else _default_db_path()
    store = SQLCipherAssuranceStore(db_path)
    try:
        store.unlock()
        result = import_store(store, seed_path, replace=not args.keep_existing)
        mode = "merged into" if args.keep_existing else "replaced"
        print(f"Seeded ({mode}) {result['counts']} from {seed_path}.")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.lock()

    if not args.with_signals:
        if anchors:
            print(f"Signals skipped ({len(anchors)} anchor(s) declared); "
                  "re-run with --with-signals to ingest them.")
        return 0
    # The anchors name entities in the engagement repository, so its root is what the SBOM
    # targets are generated against — the same root the bundle was resolved from.
    return _ingest_signals(
        anchors,
        repo_root=_engagement_root() or Path.cwd(),
        osv_base_url=getattr(args, "osv_base_url", None),
    )
