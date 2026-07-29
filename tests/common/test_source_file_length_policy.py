from __future__ import annotations

from pathlib import Path

from src.infrastructure.quality.source_file_length import (
    SOURCE_FILE_BASELINE_LIMITS,
    SOURCE_FILE_HARD_LIMIT,
    find_source_length_violations,
)


def test_non_test_source_files_do_not_exceed_length_policy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations = find_source_length_violations(repo_root)
    if not violations:
        return

    details = "\n".join(
        f"- {item.path}: {item.counted_lines} lines ({item.reason}; limit={item.limit})" for item in violations
    )
    baseline = "\n".join(
        f"- {path}: {limit}"
        for path, limit in sorted(SOURCE_FILE_BASELINE_LIMITS.items())
        if limit > SOURCE_FILE_HARD_LIMIT
    )
    raise AssertionError(
        "Non-test source file length policy violated.\n"
        f"Hard limit: {SOURCE_FILE_HARD_LIMIT} counted lines.\n"
        "Violations:\n"
        f"{details}\n"
        "Current oversized baseline:\n"
        f"{baseline}\n"
        "Refactor oversized source modules instead of growing them further."
    )
