#!/usr/bin/env python
"""Dogfooding security-signal ingest: generate an SBOM, acquire OSV data, and
submit one typed IngestBundle per anchor through the IngestSecuritySignals command.

Targets:
  python — the backend's uv environment via the pinned cyclonedx-py generator
  npm    — the GUI via `npm sbom` (npm >= 9.5), dependency graph preserved

This script is a thin CLI: acquisition lives in
``src.infrastructure.assurance.signal_sources`` and submission in
``signal_ingest``, so `arch-assurance seed --with-signals` performs the identical
act. The script never touches a signals connector and never drives the snapshot
lifecycle — the command owns staging → populate → complete → atomic activation.
`--dry-run` builds and reports the bundle without submitting anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.application.security_signals.command import (  # noqa: E402
    IngestActivated,
    IngestBundle,
)
from src.infrastructure.assurance.signal_ingest import submit_bundle  # noqa: E402
from src.infrastructure.assurance.signal_sources import (  # noqa: E402
    SBOM_TARGETS,
    build_live_bundle,
)


def report(bundle: IngestBundle) -> None:
    findings_by_band: dict[str, int] = {}
    unknown_severity = 0
    applicability_unknown = 0
    for finding in bundle.findings:
        band = finding.get("severity_band")
        if band:
            findings_by_band[str(band)] = findings_by_band.get(str(band), 0) + 1
        else:
            unknown_severity += 1
        if finding.get("applicability") == "unknown":
            applicability_unknown += 1
    diagnostics = bundle.diagnostics
    print(f"anchor:                {bundle.anchor_entity_id}")
    print(f"components:            {len(bundle.components)}")
    print(f"findings:              {len(bundle.findings)}")
    print(f"  by severity band:    {findings_by_band or '{}'}")
    print(f"  unknown severity:    {unknown_severity}")
    print(f"  applicability unknown: {applicability_unknown}")
    print(f"unmatched components:  {len(diagnostics.get('unmatched_components', []))}")  # type: ignore[arg-type]
    print(f"failed vuln fetches:   {len(diagnostics.get('failed_vulnerability_fetches', []))}")  # type: ignore[arg-type]
    print(f"not applicable (excl): {diagnostics.get('not_applicable_excluded', 0)}")


def print_outcome(result: object) -> int:
    """Report submitted vs persisted counts. Reporting only the submitted count
    would tell the caller a number it cannot read back."""
    if not isinstance(result, IngestActivated):
        print(f"result: {type(result).__name__}: {result}")
        return 1
    print(f"result: activated snapshot {result.snapshot_id}")
    print(f"  components persisted:  {result.persisted_component_count}"
          f" (of {result.submitted_component_count} submitted)")
    print(f"  findings persisted:    {result.persisted_finding_count}"
          f" (of {result.submitted_finding_count} submitted)")
    if result.collapsed_finding_count:
        print(f"  collapsed by alias:    {result.collapsed_finding_count}"
              " (findings sharing one canonical vulnerability per component)")
    return 0


def submit(bundle: IngestBundle) -> int:
    from src.infrastructure.assurance.store_factory import get_assurance_bundle  # noqa: PLC0415
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    manifest = resolve_manifest()
    assurance = get_assurance_bundle(
        REPO_ROOT,
        db_path=manifest.assurance_db_path.path,
        signals_db_path=manifest.signals_db_path.path,
    )
    if not assurance.store.is_unlocked():
        try:
            assurance.store.unlock()
        except Exception as exc:  # noqa: BLE001
            print(f"cannot unlock the assurance store: {exc}", file=sys.stderr)
            print("hint: keyring key 'db-encryption-key' or ARCH_ASSURANCE_MASTER_PASSWORD",
                  file=sys.stderr)
            return 2
    snapshot_store = assurance.snapshot_store
    if snapshot_store is None:
        print("ingest requires the SQLCipher store with co-located signals", file=sys.stderr)
        return 2
    return print_outcome(submit_bundle(bundle, snapshot_store=snapshot_store))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(SBOM_TARGETS), required=True)
    parser.add_argument("--anchor", required=True, help="architecture anchor entity id")
    parser.add_argument("--dry-run", action="store_true",
                        help="build and report the bundle; submit nothing")
    parser.add_argument("--osv-base-url", default=None)
    args = parser.parse_args()

    bundle = build_live_bundle(
        args.target, args.anchor, repo_root=REPO_ROOT, osv_base_url=args.osv_base_url,
    )
    report(bundle)
    if args.dry_run:
        print("dry run — nothing submitted")
        return 0
    return submit(bundle)


if __name__ == "__main__":
    raise SystemExit(main())
