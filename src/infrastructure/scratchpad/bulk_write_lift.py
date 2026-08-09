"""Performing a lift: the plan, handed to the write path everything else authors through.

There is no second route into the model. `artifact_bulk_write` stages the whole batch, verifies the
repository as a whole, and commits or rolls back — so a lift inherits the transaction, the refusal
vocabulary and the verification that ordinary authoring has, rather than reproducing any of them.
That is the property ADR@1783406851 exists to protect, and a feature whose whole job is to *become*
model content is exactly the one that would be tempted to route around it.

This module holds nothing but the translation: plan items become batch items, and the batch's answer
becomes a receipt correlated back to the notes and links that asked for it. Whether a thing should
be created at all was decided in `application/scratchpad/lift.py`, without touching a repository.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from src.application.scratchpad.lift import LiftItem, LiftPlan, LiftReceipt, LiftTarget


class BulkWriteLiftWriter:
    """The `LiftWriterPort`, over one engagement repository."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def resolve_target(self, group: str) -> LiftTarget:
        """What the named model-project is today.

        An unknown slug is not a refusal: "this thinking has become a project" is the normal way a
        project starts, and sending someone away to create a group first would interrupt exactly
        the moment the feature exists to serve. The plan reports `exists=False`, and execution
        creates it.
        """
        from src.application.group_registry import load_group_registry  # noqa: PLC0415

        if not group:
            return LiftTarget()
        entry = load_group_registry(self._repo_root).find("model-project", group)
        if entry is None:
            return LiftTarget(group=group, exists=False)
        return LiftTarget(group=group, meta_ontology=entry.meta_ontology, exists=True)

    def execute(self, plan: LiftPlan, *, meta_ontology: str, dry_run: bool) -> LiftReceipt:
        from src.infrastructure.mcp.artifact_mcp.bulk.write import (  # noqa: PLC0415
            artifact_bulk_write,
        )

        creates = plan.of("create")
        if not creates:
            return LiftReceipt()
        if not dry_run:
            for target in plan.targets:
                if target.group and not target.exists:
                    self._create_project(target.group, meta_ontology)

        # A reference is written *into* its document rather than beside it, so it contributes no
        # batch item of its own — `_with_references` already folded it into the document's refs.
        items = [
            _batch_item(item) for item in creates
            if item.kind not in ("reference", "diagram")
        ]
        answer = artifact_bulk_write(
            items=items,
            dry_run=dry_run,
            repo_root=str(self._repo_root),
            return_mode="full",
        )
        receipt = _receipt(answer, creates)
        drawn = next((item for item in creates if item.kind == "diagram"), None)
        if drawn is not None and receipt.committed:
            receipt = self._draw(drawn, plan, receipt)
        return receipt

    def _draw(self, item: LiftItem, plan: LiftPlan, receipt: LiftReceipt) -> LiftReceipt:
        """The view, drawn after the content committed — the only thing a lift does out of band.

        It can only name entities that exist, so it cannot be part of the batch that creates them.
        A failure here is reported and does not retract the lift: what the lift wrote is correct
        model content whether or not anyone drew a picture of it.
        """
        from src.infrastructure.write.artifact_write import diagram as diagram_ops  # noqa: PLC0415

        resolve = lambda ref: receipt.realized.get(ref.removeprefix("$ref:"), ref)  # noqa: E731
        entity_ids = [resolve(ref) for ref in item.entity_refs]
        groupings = [
            {"label": grouping.label, "entity-ids": [resolve(ref) for ref in grouping.members]}
            for grouping in plan.groupings
        ]
        try:
            result = self._create_diagram(diagram_ops, item, entity_ids, groupings)
        except Exception as exc:  # noqa: BLE001 — a picture must not be able to undo a lift
            return replace(receipt, errors=(*receipt.errors, f"{item.label} (diagram): {exc}"))
        allocated = str(result.artifact_id or "")
        return replace(
            receipt,
            realized={**receipt.realized, item.id: allocated} if allocated else receipt.realized,
        )

    def _create_diagram(
        self, diagram_ops: Any, item: LiftItem, entity_ids: list[str], groupings: list[dict[str, Any]]
    ) -> Any:
        from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415
        from src.infrastructure.mcp.artifact_mcp.bulk.common import temp_repo_callbacks  # noqa: PLC0415
        from src.infrastructure.verification.verifier_factory import build_artifact_verifier  # noqa: PLC0415

        clear_repo_caches, _touched = temp_repo_callbacks(self._repo_root)
        return diagram_ops.create_diagram(
            repo_root=self._repo_root,
            verifier=build_artifact_verifier(None, catalogs=process_runtime_catalogs()),
            clear_repo_caches=clear_repo_caches,
            diagram_type=item.artifact_type,
            name=item.label,
            puml="",
            artifact_id=None,
            entity_ids_used=entity_ids,
            authored_groupings=groupings,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=False,
            group=item.target,
        )

    def _create_project(self, slug: str, meta_ontology: str) -> None:
        """The target project, declared in the scratchpad's own vocabulary.

        Carrying `meta_ontology` matters: a project created empty and defaulted would accept the
        first content of any vocabulary, and the mismatch this lift refuses would become one a
        later lift cannot detect.
        """
        from src.infrastructure.write.artifact_write.group_ops import group_create  # noqa: PLC0415

        group_create(
            self._repo_root,
            axis="model-project",
            slug=slug,
            name=slug.replace("-", " ").strip().capitalize() or slug,
            description="Created by a scratchpad lift.",
            meta_ontology=meta_ontology,
        )


def _batch_item(item: LiftItem) -> dict[str, Any]:
    """One plan item as one batch item. The plan already decided everything this reads, including
    which project the item lands in — that is the frame's target, resolved during planning."""
    if item.kind == "element":
        create: dict[str, Any] = {
            "op": "create_entity",
            "_ref": item.id,
            "artifact_type": item.artifact_type,
            "name": item.label,
            "group": item.target,
        }
        if item.summary:
            create["summary"] = item.summary
        if item.specializations:
            create["specializations"] = list(item.specializations)
        return create
    if item.kind == "document":
        document: dict[str, Any] = {
            "op": "create_document",
            "_ref": item.id,
            "doc_type": item.artifact_type,
            "title": item.label,
            # A document collection of the same name as the project, so one target names both — the
            # alternative is asking twice for one decision a person has already made.
            "group": item.target,
        }
        if item.summary:
            document["body"] = item.summary
        if item.entity_refs:
            # One way, and recorded here: `entity_refs` becomes a `References` section of relative
            # links in the document. Nothing is written to the entity, which is what keeps a
            # document a commentary on the model rather than a second place the model is defined.
            document["entity_refs"] = list(item.entity_refs)
        return document
    return {
        "op": "add_connection",
        "_ref": item.id,
        "source_entity": item.source_ref,
        "target_entity": item.target_ref,
        "connection_type": item.artifact_type,
    }


def _receipt(answer: dict[str, object], creates: tuple[LiftItem, ...]) -> LiftReceipt:
    """The batch's answer, correlated back by position.

    `refs` maps only the entity aliases, because only `create_entity` allocates one — a connection
    reports its id on its own result row. Position is the correlation for both: `return_mode="full"`
    answers every item in input order, which is the order `execute` built them in.
    """
    rows = answer.get("items")
    results = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    realized: dict[str, str] = {}
    errors: list[str] = []
    written = [item for item in creates if item.kind not in ("reference", "diagram")]
    for item, row in zip(written, results, strict=False):
        error = row.get("error")
        if error:
            errors.append(f"{item.label}: {error}")
            continue
        allocated = row.get("artifact_id")
        if allocated:
            realized[item.id] = str(allocated)
    return LiftReceipt(
        committed=bool(answer.get("committed")),
        realized=realized,
        errors=tuple(errors),
        operation_id=str(answer.get("operation_id") or ""),
    )
