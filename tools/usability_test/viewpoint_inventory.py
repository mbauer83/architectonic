"""Snapshot the effective viewpoint catalog for usability-test ground truth.

Default mode prints one row per definition (slug, name, tier, version, representation,
purpose, content, stakeholders, concerns, parameters, description) plus criteria-catalog
facets. ``--baseline FILE`` additionally writes a restoration checksum: the full catalog
with a canonical sha256 per definition entry and the current pin list — cleanup verifies
post-run equality against it. Read-only; stdlib only.

Usage:
  python tools/usability_test/viewpoint_inventory.py [--baseline FILE] \
      [--base-url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def _get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def canonical_hash(entry: dict[str, Any]) -> str:
    """sha256 over the sorted-key JSON of the full catalog entry — a stable within-run
    identity for 'this definition did not change'."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()


def _definition_row(entry: dict[str, Any]) -> dict[str, Any]:
    presentation: dict[str, Any] = entry.get("presentation") or {}
    query: dict[str, Any] = entry.get("query") or {}
    return {
        "slug": entry.get("slug"),
        "name": entry.get("name"),
        "tier": entry.get("tier"),
        "version": entry.get("version"),
        "representation": presentation.get("representation"),
        "purpose": entry.get("purpose"),
        "content": entry.get("content"),
        "stakeholders": entry.get("stakeholders"),
        "concerns": entry.get("concerns"),
        "parameters": [
            {"name": p.get("name"), "type": p.get("type"), "required": p.get("required", True)}
            for p in (query.get("parameters") or [])
        ],
        "has_query": bool(query),
        "styling_rule_count": len(presentation.get("styling_rules") or []),
        "description": entry.get("description", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=None, metavar="FILE",
                        help="also write a full-catalog restoration checksum (hashes + pins)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    catalog = _get(args.base_url, "/api/viewpoints")
    criteria = _get(args.base_url, "/api/viewpoints/criteria-catalog")
    entries = catalog.get("viewpoints", [])

    print(json.dumps(
        {
            "viewpoints": [_definition_row(entry) for entry in entries],
            "group_slugs": criteria.get("entity_attribute_enums", {}).get("group", []),
            "entity_types": criteria.get("entity_types", []),
            "reserved_entity_paths": criteria.get("reserved_entity_paths", []),
        },
        indent=2,
    ))

    if args.baseline:
        pins = _get(args.base_url, "/api/viewpoints/pins")
        baseline = {
            "definitions": {
                str(entry.get("slug")): {
                    "tier": entry.get("tier"),
                    "version": entry.get("version"),
                    "hash": canonical_hash(entry),
                }
                for entry in entries
            },
            "pins": pins.get("slugs", []),
        }
        baseline_path = Path(args.baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written to {args.baseline}", file=sys.stderr)


if __name__ == "__main__":
    main()
