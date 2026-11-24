"""A candidate's operations written onto the model in one staged transaction, or not at all.

What is written and what refuses it are decided in `application/change_sets/candidate_apply.py`.
This module translates the operations into the bulk write's items (`to_bulk_items`) and hands them to
the bulk write's transaction core, which stages every item, verifies the repository as a whole and
commits all of them or none. The entity removals go into the same batch: the public bulk write
leaves them to the bulk delete, which would make one candidate two transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.change_sets.candidate_apply import Application
from src.application.group_registry import load_group_registry
from src.infrastructure.mcp.artifact_mcp.bulk.change_set_items import GroupName, Untranslatable, to_bulk_items
from src.infrastructure.mcp.artifact_mcp.bulk.write import CHANGE_SET_OPS, write_batch
from src.infrastructure.mcp.artifact_mcp.bulk.write_refusals import BATCH_VERIFICATION_FAILED

#: What an item says when it was refused for another item's sake: the cause is stated elsewhere.
_NOT_THE_CAUSE = ("Skipped because", "Rolled back:", BATCH_VERIFICATION_FAILED)


@dataclass(frozen=True, slots=True)
class Written:
    """What the write path answered: whether it committed, and the refusal when it would not."""

    committed: bool
    refusal: str | None
    operation_id: str | None


def write_operations(application: Application, root: Path, *, dry_run: bool) -> Written:
    """Write what *application* applies, as one batch. Nothing to write commits trivially."""
    if not application.applying.operations:
        return Written(committed=not dry_run, refusal=None, operation_id=None)
    try:
        items = to_bulk_items(
            application.applying, slug_of_group=_slug_of_group(root), resolved=application.ids,
            beneath=application.named,
        )
    except Untranslatable as refusal:
        return Written(committed=False, refusal=str(refusal), operation_id=None)
    answer = write_batch(
        items=[*items.write, *items.delete], accepted_ops=CHANGE_SET_OPS, tool_name="change_set_apply",
        dry_run=dry_run, repo_root=str(root),
    )
    return Written(
        committed=bool(answer.get("committed")), refusal=_refusal_of(answer),
        operation_id=str(answer.get("operation_id") or "") or None,
    )


def _slug_of_group(root: Path) -> GroupName:
    """A model project's directory name for its id. A set may also name it by slug, which stays."""
    slugs = {entry.id: entry.slug for entry in load_group_registry(root).model_projects}
    return lambda group: slugs.get(group, group)


def _refusal_of(answer: dict[str, Any]) -> str | None:
    """The write path's own reasons for refusing the batch, or None when it accepted it."""
    rows = answer.get("items")
    items: list[Any] = rows if isinstance(rows, list) else []
    causes = [
        str(item["error"]) for item in items
        if isinstance(item, dict) and item.get("error") and not str(item["error"]).startswith(_NOT_THE_CAUSE)
    ]
    verification = answer.get("batch_verification")
    if isinstance(verification, dict) and verification.get("executed") and not verification.get("valid"):
        causes += [
            f"{result.get('path')}: {issue.get('message')}"
            for result in verification.get("results", []) if isinstance(result, dict) and not result.get("valid")
            for issue in result.get("issues", []) if isinstance(issue, dict) and issue.get("severity") == "error"
        ]
    if causes or answer.get("failed_count"):
        return " ".join(causes) or "The write path refused the operations."
    return None
