from __future__ import annotations

from pathlib import Path

from src.infrastructure.quality.line_length import (
    LINE_LENGTH_LIMIT,
    find_line_length_violations,
)


def test_frontend_source_files_do_not_add_over_limit_lines() -> None:
    """No edited/new frontend file may increase its count of over-limit lines (Python is capped
    natively by Ruff E501). The grandfathered backlog only ratchets down."""
    repo_root = Path(__file__).resolve().parents[2]
    violations = find_line_length_violations(repo_root)
    if not violations:
        return

    details = "\n".join(
        f"- {item.path}: {item.over_limit_lines} lines over {LINE_LENGTH_LIMIT} cols "
        f"(baseline={item.baseline})"
        for item in violations
    )
    raise AssertionError(
        "Frontend line-length policy violated: a file has more lines over "
        f"{LINE_LENGTH_LIMIT} columns than its recorded baseline.\n"
        f"{details}\n"
        "Keep new/edited lines within the limit; do not raise the baseline. Lower an entry in "
        "LINE_LENGTH_BASELINE (src/infrastructure/quality/line_length.py) only when a file improves."
    )
