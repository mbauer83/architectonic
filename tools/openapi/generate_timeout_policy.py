"""Write (or check) the frontend's timeout-policy document from the route-policy manifest.

Same drift class as `types.generated.ts` and the OpenAPI types, gated the same way: the document is
committed so the frontend needs no Python to build, and `--check` fails when the committed copy and
the manifest disagree.

Usage:
    uv run tools/openapi/generate_timeout_policy.py            # write
    uv run tools/openapi/generate_timeout_policy.py --check    # fail if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DOCUMENT = (
    Path(__file__).resolve().parents[2]
    / "tools" / "gui" / "src" / "adapters" / "http" / "routeTimeoutPolicy.json"
)


def main(argv: list[str]) -> int:
    """Parsed rather than scanned for a substring.

    ``"--check" in argv`` meant every other argument — including ``--help`` — fell through to the
    *write* branch, so the one interrogative the command offers rewrote a committed file instead of
    describing itself. Same defect as ``export_doc_diagrams.py`` and ``generate_types.py`` had.
    """
    parser = argparse.ArgumentParser(prog="generate_timeout_policy.py", description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail when the committed document is stale, writing nothing"
    )
    args = parser.parse_args(argv)

    from src.infrastructure.rest.route_policy import ROUTE_POLICY
    from src.infrastructure.rest.route_policy.timeout_policy_document import serialize

    expected = serialize(ROUTE_POLICY)
    if args.check:
        current = DOCUMENT.read_text(encoding="utf-8") if DOCUMENT.exists() else ""
        if current == expected:
            return 0
        print(
            f"{DOCUMENT} is stale — run "
            "`uv run tools/openapi/generate_timeout_policy.py` and commit the result.",
            file=sys.stderr,
        )
        return 1
    DOCUMENT.write_text(expected, encoding="utf-8")
    print(f"wrote {DOCUMENT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
