"""Report — or gate — the REST operations no request has ever reached through the server.

The register in `tools/quality/operation_execution.py` is the committed answer; this script is how
the answer is re-measured. `--check` is the same comparison the fitness function
makes, but it *requires* a log rather than skipping without one, so it can be run deliberately
after a session's browser or conformance suite to find out what the session newly covered.

Usage:
    uv run tools/quality/never_requested_operations.py            # the table, and the diff
    uv run tools/quality/never_requested_operations.py --check    # non-zero if the register is wrong
    uv run tools/quality/never_requested_operations.py --log path/to/backend.log
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="never_requested_operations.py", description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the register is stale")
    parser.add_argument("--log", type=Path, default=None, help="access log to read")
    args = parser.parse_args(argv[1:])

    from src.infrastructure.rest.route_policy import BY_OPERATION, ROUTE_POLICY
    from tools.quality.operation_execution import (
        DEFAULT_REQUEST_LOG,
        NEVER_REQUESTED_OPERATIONS,
        never_requested_operations,
        parse_requested_routes,
        read_request_log,
    )

    log_path = args.log or DEFAULT_REQUEST_LOG
    log_text = read_request_log(log_path)
    if log_text is None:
        print(f"no access log at {log_path} — nothing to measure", file=sys.stderr)
        return 1

    dark = never_requested_operations(parse_requested_routes(log_text))
    declared = Counter(row.method for row in ROUTE_POLICY)
    measured = Counter(BY_OPERATION[operation].method for operation in dark)

    print(f"{'method':8} {'declared':>8} {'dark':>6} {'':>6}")
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        share = measured[method] / declared[method] if declared[method] else 0.0
        print(f"{method:8} {declared[method]:8} {measured[method]:6} {share:6.0%}")

    newly_covered = sorted(NEVER_REQUESTED_OPERATIONS - dark)
    newly_dark = sorted(dark - NEVER_REQUESTED_OPERATIONS)
    for operation in newly_covered:
        print(f"covered now, remove from the register: {operation}")
    for operation in newly_dark:
        print(f"dark and not in the register: {operation}")

    if args.check and (newly_covered or newly_dark):
        print(
            "The register disagrees with the log. Remove what is covered; exercise what is dark "
            "rather than adding it.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
