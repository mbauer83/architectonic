"""What an item of a bulk write says when the batch did not apply it.

A batch commits whole or not at all, so an item that was accepted on its own account still has
something to report once the batch is refused. Each reason here is the batch's, restated on the item
so that no item can be read as applied; the evidence for it is stated once, at batch level.
"""

from __future__ import annotations

from typing import Any

from .common import KNOWN_ITEM_FIELDS, KNOWN_OPS, unknown_item_fields

#: Points at the batch's own `batch_verification` rather than repeating its findings per item: a
#: fifty-item batch refused for one diagram would otherwise carry that diagram's issues fifty times.
BATCH_VERIFICATION_FAILED = (
    "Batch verification failed before commit; the findings are in batch_verification"
)


def unknown_op_items(
    *,
    indexed: list[tuple[int, dict[str, Any]]],
    unknown: list[tuple[int, dict[str, Any]]],
    dry_run: bool,
    operation_id: str,
) -> list[dict[str, object]]:
    results: dict[int, dict[str, object]] = {}
    for index, item in unknown:
        op = str(item.get("op", "unknown"))
        stray = unknown_item_fields(item)
        if op not in KNOWN_OPS:
            error = f"Unknown op '{item.get('op')}'"
        else:
            accepted = ", ".join(sorted(KNOWN_ITEM_FIELDS[op]))
            error = (
                f"Unknown field(s) {', '.join(repr(field) for field in stray)} for op '{op}'. "
                f"Accepted: {accepted}. A field this op does not accept is not ignored: it would "
                f"make the item do something other than what it says."
            )
        results[index] = {
            "op": item.get("op", "unknown"),
            "error": error,
            "wrote": False,
            "dry_run": dry_run,
            "operation_id": operation_id,
        }
    for index, item in indexed:
        if index not in results:
            results[index] = {
                "op": str(item.get("op", "unknown")),
                "error": "Skipped because the batch failed validation",
                "wrote": False,
                "dry_run": dry_run,
                "operation_id": operation_id,
            }
    return [results[index] for index in range(len(indexed))]


def mark_batch_aborted_by_item_failure(
    *,
    indexed: list[tuple[int, dict[str, Any]]],
    results: dict[int, dict[str, object]],
    dry_run: bool,
    operation_id: str,
) -> None:
    """Backfill a reason on items that succeeded during staging before a later
    item failed. Without this, a caller cannot tell such an item apart from one
    that silently no-op'd — items with their own real error (the failing item)
    or an explicit "Skipped because..." (items after it) already carry one.
    """
    for index, item in indexed:
        existing = results.get(index)
        if existing is None:
            results[index] = {
                "op": str(item.get("op", "unknown")),
                "error": "Skipped because an earlier batch item failed",
                "wrote": False,
                "dry_run": dry_run,
                "operation_id": operation_id,
            }
        elif "error" not in existing:
            existing["error"] = "Rolled back: a later item in this batch failed, so no changes were committed"


def mark_verification_failure(
    *,
    indexed: list[tuple[int, dict[str, Any]]],
    results: dict[int, dict[str, object]],
    dry_run: bool,
    operation_id: str,
) -> None:
    for index, item in indexed:
        existing = results.get(index)
        if existing is None:
            results[index] = {
                "op": str(item.get("op", "unknown")),
                "error": BATCH_VERIFICATION_FAILED,
                "wrote": False,
                "dry_run": dry_run,
                "operation_id": operation_id,
            }
        elif "error" not in existing:
            existing["error"] = BATCH_VERIFICATION_FAILED
