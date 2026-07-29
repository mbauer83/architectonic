"""Execute one viewpoint headlessly and dump what the engine actually returned.

Full-fidelity ground truth for oracle construction and invariant checks: the complete
raw execution result (all entity/connection records, provenance: version, executed_at,
index_generation, repo_scope, entity_limit, truncation) and the complete styled
projection (per-item style maps), plus a small derived summary. Nothing is truncated or
discarded — evidence beats brevity here. Read-only; stdlib only.

Usage:
  python tools/usability_test/execution_probe.py SLUG [--param name=value ...] \
      [--limit N] [--summary] [--out FILE] [--base-url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


def _post(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _summary(execution: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    style_capability_counts: Counter[str] = Counter()
    styled_item_ids: list[str] = []
    for item in projection.get("items", []):
        style: dict[str, Any] = item.get("style") or {}
        if style:
            styled_item_ids.append(str(item.get("item_id")))
        for capability in style:
            style_capability_counts[capability] += 1
    return {
        "slug": execution.get("slug"),
        "version": execution.get("version"),
        "repo_scope": execution.get("repo_scope"),
        "executed_at": execution.get("executed_at"),
        "index_generation": execution.get("index_generation"),
        "entity_limit": execution.get("entity_limit"),
        "entities": f"{execution.get('returned_entity_count')}/{execution.get('total_entity_count')}",
        "connections": f"{execution.get('returned_connection_count')}/{execution.get('total_connection_count')}",
        "truncated": execution.get("truncated"),
        "anchor_ids": execution.get("anchor_ids"),
        "warnings": execution.get("warnings"),
        "query_summary": execution.get("query_summary"),
        "styled_items_by_capability": dict(style_capability_counts),
        "styled_item_ids": styled_item_ids,
        "scale_legends": projection.get("scale_legends"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--summary", action="store_true", help="print only the derived summary")
    parser.add_argument("--out", default=None, metavar="FILE", help="write JSON to FILE instead of stdout")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    parameters = dict(item.split("=", 1) for item in args.param)
    body: dict[str, Any] = {"slug": args.slug}
    if parameters:
        body["parameters"] = parameters
    if args.limit is not None:
        body["limit"] = args.limit

    execution = _post(args.base_url, "/api/viewpoints/execute", body)
    projection = _post(args.base_url, "/api/viewpoints/execute-projection", body)

    summary = _summary(execution, projection)
    execution_generation = execution.get("index_generation")
    projection_generation = projection.get("index_generation")
    summary["projection_index_generation"] = projection_generation
    if projection_generation is None:
        summary["generation_consistency"] = "unverifiable (backend predates projection provenance)"
    elif projection_generation == execution_generation:
        summary["generation_consistency"] = "same-snapshot"
    payload: dict[str, Any] = (
        summary if args.summary else {"summary": summary, "execution": execution, "projection": projection}
    )
    text = json.dumps(payload, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    if projection_generation is not None and projection_generation != execution_generation:
        print(
            f"GENERATION MISMATCH: execution at {execution_generation}, projection at "
            f"{projection_generation} — the model changed mid-pair; re-run the probe",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
