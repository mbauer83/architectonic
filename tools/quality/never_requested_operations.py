"""Report — or gate — the REST operations no request has ever reached through the server.

The register in `tools/quality/operation_execution.py` is the committed answer; this script is how
the answer is re-measured. `--check` is the same comparison the fitness function
makes, but it *requires* a log rather than skipping without one, so it can be run deliberately
after a session's browser or conformance suite to find out what the session newly covered.

Usage:
    uv run tools/quality/never_requested_operations.py            # the table, and the diff
    uv run tools/quality/never_requested_operations.py --check    # non-zero if the register is wrong
    uv run tools/quality/never_requested_operations.py --log path/to/backend.log
    uv run tools/quality/never_requested_operations.py --log a.log --log b.log   # union of both

`--log` is repeatable because coverage no longer comes from one process. The dogfood backend's log holds
what the browser and conformance suites reached; the REST write walk runs against its *own* fixture
backend on its own port, and writes its log wherever `--log-out` says. Reading only one of them reports
operations as dark that a walk requests every run — a register that understates coverage teaches people
to distrust it, which is the same failure as overstating it.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="never_requested_operations.py", description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when any operation is dark")
    parser.add_argument(
        "--log", type=Path, action="append", default=None,
        help="access log to read; repeat to union several (dogfood backend + fixture write walk)",
    )
    args = parser.parse_args(argv[1:])

    from src.infrastructure.rest.route_policy import BY_OPERATION, ROUTE_POLICY
    from tools.quality.operation_execution import (
        DEFAULT_REQUEST_LOG,
        never_requested_operations,
        parse_requested_routes,
        read_request_log,
    )

    log_paths = args.log or [DEFAULT_REQUEST_LOG]
    texts = [(path, read_request_log(path)) for path in log_paths]
    missing = [str(path) for path, text in texts if text is None]
    if missing:
        print(f"no access log at {', '.join(missing)} — nothing to measure", file=sys.stderr)
        return 1

    # Union of the requests, not of the darkness: an operation is covered if *any* log shows it
    # answering 2xx, and intersecting the dark sets instead would let one log's silence hide another's
    # evidence.
    routes: frozenset[Any] = frozenset()
    for _path, text in texts:
        routes |= parse_requested_routes(text or "")
    dark = never_requested_operations(routes, ROUTE_POLICY)
    declared = Counter(row.method for row in ROUTE_POLICY)
    measured = Counter(BY_OPERATION[operation].method for operation in dark)

    print(f"{'method':8} {'declared':>8} {'dark':>6} {'':>6}")
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        share = measured[method] / declared[method] if declared[method] else 0.0
        print(f"{method:8} {declared[method]:8} {measured[method]:6} {share:6.0%}")

    # No register to diff against. It reached empty — every operation the surface serves has been
    # requested — and an allowlist that must stay empty is a conditional in every consumer rather than
    # a fact, which is the lesson `route_policy/_pending.py` already paid for. What is dark is now
    # simply what is dark.
    for operation in sorted(dark):
        print(f"dark: {operation}")

    if args.check and dark:
        print(
            f"{len(dark)} operation(s) are served and nothing has ever requested one. Exercise each "
            "through the running server rather than recording it.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
