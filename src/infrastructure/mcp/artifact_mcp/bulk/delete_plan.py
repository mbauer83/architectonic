"""Request parsing and planning helpers for bulk delete."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.domain.artifact_id import ConnectionKey

#: How a connection is identified within one delete batch: source, type, target — normalised, so a
#: symmetric relationship has one key whichever endpoint names it. The tuple is what the batch's
#: sets and dicts are keyed on; `ConnectionKey` is the domain value that knows the normalisation.
BatchKey = tuple[str, str, str]


#: How a batch names a connection: `(source, type, target)` -> its key.
KeyOf = Callable[[str, str, str], BatchKey]


def key_function(is_symmetric: Callable[[str], bool]) -> KeyOf:
    """The key both sides of a batch compare on, bound to one answer about symmetry.

    A symmetric relationship has no direction, so `(A, type, B)` and `(B, type, A)` name the same
    connection and must produce the same key. Comparing the raw triples meant a batch could not
    recognise its own connection delete when the entity delete named the other endpoint, and the
    author had to run the two deletes in separate passes to get past a blocker that was already
    satisfied.

    Bound once and passed, rather than each side asking for itself: the whole failure was two places
    answering the same question differently.
    """

    def key_of(source: str, conn_type: str, target: str) -> BatchKey:
        endpoints = ConnectionKey(src_short=source, type=conn_type, tgt_short=target)
        normalised = endpoints.normalized(symmetric=is_symmetric(conn_type))
        return (normalised.src_short, normalised.type, normalised.tgt_short)

    return key_of


def validation_error(op: str, message: str) -> dict[str, object]:
    return {"op": op, "error": message, "wrote": False, "dry_run": True}


def collect_requests(
    indexed: list[tuple[int, dict[str, Any]]],
    *,
    key_of: KeyOf,
) -> tuple[
    dict[BatchKey, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    list[tuple[int, str, str]],
]:
    explicit_connection_deletes: dict[BatchKey, int] = {}
    entity_deletes: dict[str, int] = {}
    document_deletes: dict[str, int] = {}
    diagram_deletes: dict[str, int] = {}
    duplicate_errors: list[tuple[int, str, str]] = []
    id_buckets = {
        "delete_entity": entity_deletes,
        "delete_document": document_deletes,
        "delete_diagram": diagram_deletes,
    }

    for index, item in indexed:
        op = str(item.get("op", ""))
        if op == "delete_connection":
            try:
                key = key_of(
                    str(item["source_entity"]),
                    str(item["connection_type"]),
                    str(item["target_entity"]),
                )
            except KeyError as exc:
                duplicate_errors.append((index, op, f"Missing required field: {exc.args[0]}"))
                continue
            if key in explicit_connection_deletes:
                duplicate_errors.append((index, op, f"Duplicate delete_connection request for {key}"))
            else:
                explicit_connection_deletes[key] = index
            continue

        try:
            artifact_id = str(item["artifact_id"])
        except KeyError as exc:
            duplicate_errors.append((index, op, f"Missing required field: {exc.args[0]}"))
            continue
        bucket = id_buckets[op]
        if artifact_id in bucket:
            duplicate_errors.append((index, op, f"Duplicate {op} request for '{artifact_id}'"))
        else:
            bucket[artifact_id] = index

    return (
        explicit_connection_deletes,
        entity_deletes,
        document_deletes,
        diagram_deletes,
        duplicate_errors,
    )


def planned_steps(
    *,
    indexed: list[tuple[int, dict[str, Any]]],
    entity_order: list[str],
) -> list[dict[str, Any]]:
    entity_rank = {artifact_id: pos for pos, artifact_id in enumerate(entity_order)}
    planned: list[dict[str, Any]] = []
    for index, item in indexed:
        op = str(item.get("op", ""))
        if op == "delete_connection":
            planned.append({"phase": 0, "index": index, "item": item})
        elif op == "delete_diagram":
            planned.append({"phase": 1, "index": index, "item": item})
        elif op == "delete_document":
            planned.append({"phase": 2, "index": index, "item": item})
        elif op == "delete_entity":
            planned.append(
                {
                    "phase": 3,
                    "phase_order": entity_rank[str(item["artifact_id"])],
                    "index": index,
                    "item": item,
                }
            )
    planned.sort(key=lambda step: (int(step["phase"]), int(step.get("phase_order", 0)), int(step["index"])))
    return planned
