"""ModelAndBind: orchestrate alleviating a modelling gap from assurance work.

When an assurance node references something not (well) modelled — an
``unbound-pending`` control-structure node, a hazard on an unmodelled component —
this use case either:

  * **Bound** — when an architecture-write capability is supplied: create the
    proposed architecture entity, register the one-way assurance→architecture
    reference, and mark the node ``bound``. Cross-repository atomicity is never
    claimed: if binding fails *after* the entity is created, the node is left
    ``unbound-pending`` and a compensating task is returned.
  * **TaskRequired** — when no write capability is supplied or separation of
    duties is requested: emit a structured task telling an architecture-write
    session what to create and how to bind it back.

The architecture-write capability is injected as the ``ArchitectureEntityCreator``
port, so this application use case never depends on an architecture adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from src.application import assurance_mutations as mutations

if TYPE_CHECKING:
    from src.application.assurance_ports import AssuranceArchive, ConfidentialAssuranceStore

_BIND_REF_TYPE = "binds-to"


@runtime_checkable
class ArchitectureEntityCreator(Protocol):
    """Optional architecture-write port for the Bound path.

    Adapters wrap the architecture repository's create path. ``is_known_type``
    validates the proposed type before any write is attempted.
    """

    def is_known_type(self, artifact_type: str) -> bool: ...

    def create(self, artifact_type: str, name: str) -> str: ...


# ── Typed outcomes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Bound:
    """Architecture entity created and bound to the assurance node."""

    assurance_node_id: str
    arch_artifact_id: str
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TaskRequired:
    """No write capability (or separation of duties); a structured task is returned."""

    spec: dict[str, Any]


@dataclass(frozen=True)
class BindLocked:
    """Store not unlocked; HTTP 423 / MCP locked envelope."""


@dataclass(frozen=True)
class BindNotFound:
    """Assurance node absent; HTTP 404 / MCP not_found."""

    assurance_node_id: str


@dataclass(frozen=True)
class BindInvalid:
    """Request violated a precondition (wrong binding status, unknown type); HTTP 400/409."""

    error: str
    message: str


ModelBindResult = Bound | TaskRequired | BindLocked | BindNotFound | BindInvalid


# ── Task spec ───────────────────────────────────────────────────────────────────


def build_task_spec(
    assurance_node_id: str,
    assurance_node_name: str,
    suggested_arch_type: str,
    suggested_name: str,
    domain: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Build the three-step architecture-write task for the separation-of-duties path."""
    spec: dict[str, Any] = {
        "assurance_node_id": assurance_node_id,
        "assurance_node_name": assurance_node_name,
        "action_required": "create_arch_entity_then_bind",
        "step_1": {
            "call": "artifact_create_entity",
            "on_server": "arch-repo-write",
            "params": {
                "artifact_type": suggested_arch_type,
                "name": suggested_name,
                "domain": domain,
                "dry_run": True,
            },
            "note": (
                "Call with dry_run=true first to preview, then false to create. "
                "Capture the returned entity_id for step 2."
            ),
        },
        "step_2": {
            "call": "assurance_register_arch_ref",
            "on_server": "arch-assurance-write",
            "params": {
                "assurance_node_id": assurance_node_id,
                "arch_artifact_id": "<entity_id_from_step_1>",
                "ref_type": _BIND_REF_TYPE,
            },
        },
        "step_3": {
            "call": "assurance_edit_node",
            "on_server": "arch-assurance-write",
            "params": {"node_id": assurance_node_id, "binding_status": "bound"},
        },
    }
    if note:
        spec["note"] = note
    return spec


# ── Use case ────────────────────────────────────────────────────────────────────


def model_and_bind(
    store: ConfidentialAssuranceStore,
    archive: AssuranceArchive,
    *,
    assurance_node_id: str,
    suggested_arch_type: str,
    suggested_name: str,
    domain: str = "application",
    arch_creator: ArchitectureEntityCreator | None = None,
) -> ModelBindResult:
    if not store.is_unlocked():
        return BindLocked()
    node = store.get_node(assurance_node_id)
    if node is None:
        return BindNotFound(assurance_node_id)
    binding_status = str(node.get("binding_status") or "")
    if binding_status != "unbound-pending":
        return BindInvalid(
            "invalid_binding_status",
            "model-and-bind only applies to nodes with binding_status='unbound-pending'; "
            f"node is {binding_status or 'unset'!r}.",
        )
    node_name = str(node.get("name", ""))

    # No write capability, or caller asked for separation of duties → emit a task.
    if arch_creator is None:
        return TaskRequired(
            build_task_spec(
                assurance_node_id, node_name, suggested_arch_type, suggested_name, domain
            )
        )

    if not arch_creator.is_known_type(suggested_arch_type):
        return BindInvalid(
            "unknown_arch_type",
            f"Unknown architecture entity type: {suggested_arch_type!r}.",
        )

    # Two-repository write — never atomic. Create first, then bind.
    arch_artifact_id = arch_creator.create(suggested_arch_type, suggested_name)
    ref_result = mutations.register_arch_ref(
        store, archive,
        assurance_node_id=assurance_node_id,
        arch_artifact_id=arch_artifact_id,
        ref_type=_BIND_REF_TYPE,
    )
    if not isinstance(ref_result, mutations.MutationOk):
        # Entity exists but the binding did not land — leave the node unbound-pending
        # and hand back a compensating task that references the already-created entity.
        return TaskRequired(
            build_task_spec(
                assurance_node_id, node_name, suggested_arch_type, suggested_name, domain,
                note=(
                    f"Architecture entity {arch_artifact_id} was created but the assurance "
                    "binding did not complete; node left unbound-pending. Complete steps 2–3 "
                    "with this entity_id."
                ),
            )
        )
    edit_result = mutations.edit_node(
        store, archive, node_id=assurance_node_id, binding_status="bound",
    )
    findings = edit_result.findings if isinstance(edit_result, mutations.MutationOk) else []
    archive.append(
        "MODEL_AND_BIND",
        node_id=assurance_node_id,
        payload={"arch_artifact_id": arch_artifact_id, "arch_type": suggested_arch_type},
    )
    return Bound(
        assurance_node_id=assurance_node_id,
        arch_artifact_id=arch_artifact_id,
        findings=findings,
    )
