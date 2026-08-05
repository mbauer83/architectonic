"""What `artifact_bulk_write` answers, and how much of it.

The primary caller of this surface is an agent, so the size of a reply is a design property rather
than a cosmetic one — the same reason `artifact_verify` takes a `return_mode` and
`artifact_query_list_artifacts` takes a field projection. Bulk write was the outlier and the tool most
likely to be called with fifty items: it answered fifty objects, each repeating the batch's
`operation_id` and carrying an absolute path derivable from the id, and none of them echoing the
`_ref` alias the caller used — so correlating an alias to its allocated id relied on input order
surviving the documented auto-sort, an implicit contract nobody stated.

**One shape in every mode.** `return_mode` decides how much `items` carries, never whether the reply
is a list or an object: a caller that has to branch on the mode to find the ids has been given a
second contract rather than a smaller one.
"""

from __future__ import annotations

from typing import Literal

#: `summary` is the default, as on `artifact_verify` — the compact answer is the useful one, and the
#: one an agent can afford to read. `full` is every item as it was applied; `ids` is the correlation
#: map and the counts alone, for a caller that only needs to know what its aliases became.
BulkWriteReturnMode = Literal["summary", "full", "ids"]

#: Item fields that say the same thing for every item in the batch, or restate what the batch already
#: reports. Dropped from `items` because a fifty-item reply repeated them fifty times.
_BATCH_LEVEL_ITEM_FIELDS = ("operation_id",)

#: Derivable from `artifact_id`, the artifact's group and its type — and the longest field per item.
#: Kept in `full`, which exists to be complete, and dropped from the compact modes.
_DERIVABLE_ITEM_FIELDS = ("path",)


def _without(item: dict[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key not in fields}


def _needs_reporting(item: dict[str, object]) -> bool:
    """Whether an item has something to say beyond "it was applied as asked"."""
    return bool(item.get("error")) or bool(item.get("warnings"))


def items_for(items: list[dict[str, object]], return_mode: BulkWriteReturnMode) -> list[dict[str, object]]:
    """The per-item entries a mode carries, in input order."""
    if return_mode == "ids":
        return []
    if return_mode == "full":
        return [_without(item, _BATCH_LEVEL_ITEM_FIELDS) for item in items]
    return [
        _without(item, _BATCH_LEVEL_ITEM_FIELDS + _DERIVABLE_ITEM_FIELDS)
        for item in items
        if _needs_reporting(item)
    ]


def counts_by_op(items: list[dict[str, object]]) -> dict[str, int]:
    """How many items of each op the batch carried, in the order the ops first appeared."""
    counts: dict[str, int] = {}
    for item in items:
        op = str(item.get("op", "unknown"))
        counts[op] = counts.get(op, 0) + 1
    return counts


def build_write_payload(
    *,
    items: list[dict[str, object]],
    ref_map: dict[str, str],
    operation_id: str,
    dry_run: bool,
    committed: bool,
) -> dict[str, object]:
    """The batch's complete record: its own facts, and every item as it was applied.

    Complete on purpose. This is what the operation registry keeps, so `artifact_get_operation` can
    answer about a batch in full, and so a replay under a different `return_mode` has something to
    narrow — a stored summary could never be widened back.

    `refs` is the map most callers actually need from a successful create, and it is stated rather
    than reconstructed: the alias the caller chose against the id the repository allocated.
    """
    failed = [item for item in items if item.get("error")]
    return {
        "operation_id": operation_id,
        "dry_run": dry_run,
        "committed": committed,
        "item_count": len(items),
        "failed_count": len(failed),
        "counts": counts_by_op(items),
        "refs": dict(ref_map),
        "return_mode": "full",
        "items": [_without(item, _BATCH_LEVEL_ITEM_FIELDS) for item in items],
    }


def shape_payload(payload: dict[str, object], return_mode: BulkWriteReturnMode) -> dict[str, object]:
    """The complete record, narrowed to what this call asked for.

    Applied on the way out rather than while building, so the same batch can be replayed at a
    different level of detail: an idempotency key names one logical batch, not one verbosity.
    """
    stored = payload.get("items")
    items = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    return {**payload, "return_mode": return_mode, "items": items_for(items, return_mode)}
