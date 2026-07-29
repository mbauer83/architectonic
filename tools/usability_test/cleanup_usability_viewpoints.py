"""Delete the viewpoints a usability-test run created, then verify full restoration.

Defense in depth — a deletion target must pass ALL of:
  1. listed in the run manifest ({"run_id": ..., "created_slugs": [...]});
  2. slug starts with `usability-<run_id>-` (the manifest's own run_id);
  3. absent from the pre-run baseline (so a malformed manifest can never name a
     pre-existing definition);
  4. a unique, non-empty string.
`--apply` REQUIRES `--baseline`: deletion without restoration verification is not
offered. Any validation failure, unsuccessful deletion, or post-run difference from
baseline (changed hash, missing slug, unexpected slug, pin change) exits non-zero —
stop and ask the user. Dry-run by default.

Usage:
  python tools/usability_test/cleanup_usability_viewpoints.py --manifest RUN_MANIFEST.json \
      --baseline BASELINE.json [--apply] [--base-url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from typing import Any


def canonical_hash(entry: dict[str, Any]) -> str:
    """Must stay identical to viewpoint_inventory.canonical_hash (kept dependency-free
    so this safety-critical script is importable in isolation for testing)."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()


def validate_targets(manifest: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    """The deletion-eligible slugs, or raise ValueError describing every violation."""
    problems: list[str] = []
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        problems.append("manifest has no run_id")
        run_id = ""
    raw = manifest.get("created_slugs", [])
    if not isinstance(raw, list):
        problems.append("created_slugs is not a list")
        raw = []
    slugs: list[str] = []
    prefix = f"usability-{run_id}-"
    baseline_slugs = set((baseline or {}).get("definitions", {}))
    for item in raw:
        if not isinstance(item, str) or not item:
            problems.append(f"non-string manifest entry: {item!r}")
            continue
        if item in slugs:
            problems.append(f"duplicate manifest entry: {item}")
            continue
        if run_id and not item.startswith(prefix):
            problems.append(f"slug outside this run's namespace ({prefix}*): {item}")
            continue
        if item in baseline_slugs:
            problems.append(f"slug existed before the run (baseline) — refusing to delete: {item}")
            continue
        slugs.append(item)
    if problems:
        raise ValueError("; ".join(problems))
    return slugs


def verify_against_baseline(
    catalog: dict[str, Any], pins: list[str], baseline: dict[str, Any], deleted: set[str]
) -> list[str]:
    """Differences between the post-cleanup state and the pre-run baseline."""
    problems: list[str] = []
    current = {str(entry.get("slug")): entry for entry in catalog.get("viewpoints", [])}
    expected = baseline.get("definitions", {})
    for slug, recorded in expected.items():
        entry = current.get(slug)
        if entry is None:
            problems.append(f"baseline definition missing after cleanup: {slug}")
        elif canonical_hash(entry) != recorded.get("hash"):
            problems.append(f"baseline definition changed during run: {slug}")
    for slug in current:
        if slug not in expected:
            label = "residual test slug" if slug in deleted else "unexpected new slug"
            problems.append(f"{label}: {slug}")
    if pins != baseline.get("pins", []):
        problems.append(f"pin list changed: baseline={baseline.get('pins')} current={pins}")
    return problems


def _get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, metavar="FILE")
    parser.add_argument("--baseline", default=None, metavar="FILE")
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    if args.apply and not args.baseline:
        print("--apply requires --baseline (deletion without restoration verification is not offered)",
              file=sys.stderr)
        raise SystemExit(1)

    with open(args.manifest, encoding="utf-8") as handle:
        manifest = json.load(handle)
    baseline: dict[str, Any] | None = None
    if args.baseline:
        with open(args.baseline, encoding="utf-8") as handle:
            baseline = json.load(handle)

    try:
        targets = validate_targets(manifest, baseline)
    except ValueError as exc:
        print(f"manifest validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not targets:
        print("manifest lists no deletable slugs")
    for slug in targets:
        result = _post(args.base_url, "/api/viewpoints/remove", {"slug": slug, "dry_run": not args.apply})
        outcome = "deleted" if (args.apply and result.get("ok")) else f"dry-run ok={result.get('ok')}"
        print(f"{slug}: {outcome}")
        if args.apply and not result.get("ok"):
            print(f"deletion failed for {slug} — stopping immediately; state is partial", file=sys.stderr)
            raise SystemExit(1)
    if not args.apply:
        print("(dry-run — re-run with --apply to delete)")
        return

    assert baseline is not None
    catalog = _get(args.base_url, "/api/viewpoints")
    pins = _get(args.base_url, "/api/viewpoints/pins").get("slugs", [])
    problems = verify_against_baseline(catalog, pins, baseline, set(targets))
    if problems:
        for problem in problems:
            print(f"VERIFICATION FAILURE: {problem}", file=sys.stderr)
        print("repository NOT verifiably restored — stop and ask the user", file=sys.stderr)
        raise SystemExit(1)
    print("post-cleanup verification passed: catalog and pins match baseline")


if __name__ == "__main__":
    main()
