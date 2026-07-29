"""Request parsing and planning helpers for bulk delete."""

from __future__ import annotations

from typing import Any

ConnectionKey = tuple[str, str, str]


def validation_error(op: str, message: str) -> dict[str, object]:
    return {"op": op, "error": message, "wrote": False, "dry_run": True}


def collect_requests(
    indexed: list[tuple[int, dict[str, Any]]],
) -> tuple[
    dict[ConnectionKey, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    list[tuple[int, str, str]],
]:
    explicit_connection_deletes: dict[ConnectionKey, int] = {}
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
                key = (
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
