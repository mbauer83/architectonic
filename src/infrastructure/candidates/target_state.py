"""Applying a candidate as a target state, and moving the target state into the baseline.

Shared by the HTTP and MCP transports. What is written is generated in `application/change_sets`
(`target_state.target_plan`, `target_move.move_into_baseline`) and judged by the rule a direct apply is
judged by (`candidate_apply.judged`); both go to the model through `apply.write_operations`, the one
staged write a direct apply uses.

**The order of the two writes differs, for a reason each.** Applying as a target state records it on the
candidate first, over the version read, and then writes the model; a refused or failed write takes the
record back. Recorded afterwards, a candidate changed in between would describe a target state its
operations no longer say, and an apply repeated after a lost mark would write the target state twice.
Moving into the baseline writes the model first and then clears the record, as a direct apply marks a
candidate integrated: a repeated move finds every operation already there, writes nothing, and records.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic_core import to_jsonable_python

from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_apply import INTEGRATED, Application, application_of, judged
from src.application.change_sets.candidate_architecture import DRAFT, CandidateArchitecture, CandidateState
from src.application.change_sets.candidate_reads import live_reading, wire_standing
from src.application.change_sets.candidate_recorded_form import to_mapping
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.change_sets.stacking import sets_beneath, stack_of
from src.application.change_sets.standing import standing_of
from src.application.change_sets.target_move import move_into_baseline
from src.application.change_sets.target_state import TargetPlan, target_plan
from src.application.change_sets.target_withdraw import withdrawal_of
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.target_state_relations import TargetStateRelations
from src.infrastructure.app_bootstrap import get_module_registry
from src.infrastructure.artifact_index import notify_paths_changed
from src.infrastructure.candidates.apply import Written, write_operations
from src.infrastructure.candidates.repository import CandidateConflict
from src.infrastructure.candidates.service import CandidateService, minted_entity_id

#: The state a candidate is in while its target state is in the model: offered, and no longer drafted.
OFFERED: CandidateState = "candidate"


def apply_as_target_state(service: CandidateService, ref: str, *, dry_run: bool) -> dict[str, Any]:
    """Write *ref* into the model as a target state beside the baseline, and record where it stands.

    Refused as a direct apply is — terminal, a parent not integrated, a conflicting or drifted operation —
    and also when its target state is already in the model. A dry run answers what would be written.
    """
    candidate = service.store.require(ref)
    application = application_of(candidate, service.store, service.registry)
    refusal = application.refusal
    plan = None if refusal else _plan(service, candidate)
    answer = _answer(candidate, application, plan, dry_run=dry_run, refusal=refusal)
    if refusal and not dry_run:
        raise CandidateConflict(refusal)
    if plan is None or refusal or dry_run:
        return answer
    version = record_revision(to_mapping(candidate))
    recorded = replace(candidate, state=OFFERED, target_state=plan.state)
    service.store.save(recorded, version, applied=True)
    written = _written(service, application, plan)
    if not written.committed:
        service.store.save(candidate, record_revision(to_mapping(recorded)), applied=True)
        raise CandidateConflict(written.refusal or "The write path did not commit the target state.")
    notify_paths_changed([service.store.path(candidate.id)])
    return answer | {"applied": True, "operation_id": written.operation_id}


def move_target_into_baseline(service: CandidateService, ref: str, *, dry_run: bool) -> dict[str, Any]:
    """Apply *ref*'s kept operations to the originals and take its target state away, then integrate it."""
    candidate = service.store.require(ref)
    state = candidate.target_state
    if state is None:
        refusal = f"{candidate.id} is not in the model as a target state, so there is nothing to move."
        if not dry_run:
            raise CandidateConflict(refusal)
        return {"candidate": candidate.id, "dry_run": dry_run, "integrated": False, "refusal": refusal,
                "standing": [], "operations": []}
    stack = stack_of(candidate, service.store.find)
    # The elements at the far end of a copy's relations are read too: a relation moved back needs them.
    near = live_reading(stack, service.registry, also=(*state.written, *state.added.values()))
    live = live_reading(stack, service.registry, also=(
        *state.written, *state.added.values(), *(end for address in near.connections for end in address.endpoints),
    ))
    revision = service.index.read_model_version().etag
    move = move_into_baseline(candidate, state, live, revision=revision, relations=target_state_relations())
    moving = replace(candidate, changes=move, target_state=None)
    application = judged(moving, stack, standing_of(move, live, beneath=sets_beneath(stack)))
    written = None if application.refusal else write_operations(application, service.root, dry_run=dry_run)
    refusal = application.refusal or (written.refusal if written else None)
    if refusal and not dry_run:
        raise CandidateConflict(refusal)
    integrated = bool(written and written.committed) and _integrated(service, candidate)
    return {
        "candidate": candidate.id, "dry_run": dry_run, "integrated": integrated, "refusal": refusal,
        "operation_id": written.operation_id if written else None,
        "standing": wire_standing(application.standing),
        "operations": to_jsonable_python([operation_to_mapping(operation) for operation in move.operations]),
    }


def withdraw_target_state(service: CandidateService, ref: str, *, dry_run: bool) -> dict[str, Any]:
    """Take *ref*'s target state out of the model and release the candidate as a draft.

    Removes what applying it as a target state wrote — the copies with their relations and traces, the elements
    it added, the plateaus and the gap — as one generated list through the one write path. Refused (409) while
    something written since refers to one of those elements: a relation the target state did not write, or a
    diagram drawing one. A dry run answers the operations and the refusal. The model is written first and the
    record cleared after, as a move into the baseline does, so a repeated withdrawal writes nothing and records.
    """
    candidate = service.store.require(ref)
    state = candidate.target_state
    if state is None:
        return _not_targeted(candidate.id, "withdraw", dry_run=dry_run)
    stack = stack_of(candidate, service.store.find)
    written = (*state.written, *state.added.values())
    live = live_reading(stack, service.registry, also=(*written, *state.copies))
    drawn: dict[str, list[str]] = {}
    for element in written:
        for diagram in service.index.diagrams_referencing_artifact(element):
            drawn.setdefault(diagram.artifact_id, []).append(element)
    withdrawal = withdrawal_of(
        candidate, state, live, revision=service.index.read_model_version().etag,
        relations=target_state_relations(), drawn_by=drawn,
    )
    application = Application(
        candidate=candidate, standing=standing_of(withdrawal.changes, live), applying=withdrawal.changes,
        named=ChangeSet((), withdrawal.changes.repository_revision), ids={}, refusal=withdrawal.refusal,
    )
    written_now = None if application.refusal else write_operations(application, service.root, dry_run=dry_run)
    refusal = application.refusal or (written_now.refusal if written_now else None)
    if refusal and not dry_run:
        raise CandidateConflict(refusal)
    released = bool(written_now and written_now.committed) and _released(service, candidate)
    return {
        "candidate": candidate.id, "dry_run": dry_run, "released": released, "refusal": refusal,
        "operation_id": written_now.operation_id if written_now else None,
        "operations": to_jsonable_python([operation_to_mapping(op) for op in withdrawal.changes.operations]),
    }


def _not_targeted(candidate: str, verb: str, *, dry_run: bool) -> dict[str, Any]:
    refusal = f"{candidate} is not in the model as a target state, so there is nothing to {verb}."
    if not dry_run:
        raise CandidateConflict(refusal)
    return {"candidate": candidate, "dry_run": dry_run, "refusal": refusal, "operations": []}


def _released(service: CandidateService, withdrawn: CandidateArchitecture) -> bool:
    """Record that *withdrawn*'s target state is out of the model: a draft again, with no target state."""
    for _attempt in range(3):
        current = service.store.require(withdrawn.id)
        if current.target_state is None:
            return True
        try:
            service.store.save(
                replace(current, state=DRAFT, target_state=None), record_revision(to_mapping(current)), applied=True,
            )
        except CandidateConflict:
            continue
        notify_paths_changed([service.store.path(withdrawn.id)])
        return True
    return False


def _plan(service: CandidateService, candidate: CandidateArchitecture) -> TargetPlan:
    stack = stack_of(candidate, service.store.find)
    registry = get_module_registry()
    rules = registry.aggregated_permitted_relationships()
    return target_plan(
        candidate, live_reading(stack, service.registry),
        revision=service.index.read_model_version().etag,
        allocate=minted_entity_id,
        permits=lambda source, target, kind: rules.permits(
            EntityTypeName(source), EntityTypeName(target), ConnectionTypeName(kind),
        ),
        relations=target_state_relations(),
        beneath=sets_beneath(stack),
    )


def target_state_relations() -> TargetStateRelations:
    """The relations a target state is written with, as the deployment's ontology declares them.

    Refused where no ontology declares them: a target state cannot be written in a vocabulary that has no
    way to trace a copy to its original.
    """
    relations = get_module_registry().target_state_relations()
    if relations is None:
        raise ValueError("No ontology in this deployment declares how a target state is related, so none can be "
                         "written.")
    return relations


def _written(service: CandidateService, application: Application, plan: TargetPlan) -> Written:
    try:
        return write_operations(replace(application, applying=plan.changes), service.root, dry_run=False)
    except Exception:
        current = service.store.require(application.candidate.id)
        service.store.save(application.candidate, record_revision(to_mapping(current)), applied=True)
        raise


def _answer(
    candidate: CandidateArchitecture, application: Application, plan: TargetPlan | None,
    *, dry_run: bool, refusal: str | None,
) -> dict[str, Any]:
    return {
        "candidate": candidate.id, "dry_run": dry_run, "applied": False, "refusal": refusal,
        "standing": wire_standing(application.standing),
        **({
            "target_state": {
                "baseline": plan.state.baseline, "target": plan.state.target, "gap": plan.state.gap,
                "copies": dict(plan.state.copies), "added": dict(plan.state.added),
            },
            "operations": to_jsonable_python([operation_to_mapping(op) for op in plan.shown]),
            "unheld": list(plan.unheld),
        } if plan else {}),
    }


def _integrated(service: CandidateService, moved: CandidateArchitecture) -> bool:
    """Record that *moved*'s target state is in the baseline: integrated, with no target state left.

    The model write has committed, so a header edit made meanwhile is no reason to leave it unmarked; it is
    read again and marked over its current version. Its operations cannot have changed: the target state
    holds them.
    """
    for _attempt in range(3):
        current = service.store.require(moved.id)
        if current.state == INTEGRATED:
            return True
        try:
            service.store.save(
                replace(current, state=INTEGRATED, target_state=None), record_revision(to_mapping(current)),
                applied=True,
            )
        except CandidateConflict:
            continue
        notify_paths_changed([service.store.path(moved.id)])
        return True
    return False
