"""Default diagram-type registrations."""

from __future__ import annotations

from src.diagram_types.activity import module as activity
from src.diagram_types.archimate.application import module as archimate_application
from src.diagram_types.archimate.business import module as archimate_business
from src.diagram_types.archimate.implementation import module as archimate_implementation
from src.diagram_types.archimate.layered import module as archimate_layered
from src.diagram_types.archimate.motivation import module as archimate_motivation
from src.diagram_types.archimate.strategy import module as archimate_strategy
from src.diagram_types.archimate.technology import module as archimate_technology
from src.diagram_types.bowtie import module as bowtie
from src.diagram_types.c4.component import module as c4_component
from src.diagram_types.c4.container import module as c4_container
from src.diagram_types.c4.deployment import module as c4_deployment
from src.diagram_types.c4.system_context import module as c4_system_context
from src.diagram_types.c4.system_landscape import module as c4_system_landscape
from src.diagram_types.control_structure import module as control_structure
from src.diagram_types.datatype import module as datatype
from src.diagram_types.fmea_matrix import module as fmea_matrix
from src.diagram_types.gsn import module as gsn
from src.diagram_types.matrix import module as matrix
from src.diagram_types.sequence import module as sequence
from src.diagram_types.uca_matrix import module as uca_matrix
from src.domain.modules.module_filter import is_module_enabled
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule

DEFAULT_DIAGRAM_KINDS: tuple[DiagramTypeModule, ...] = (
    activity,
    sequence,
    datatype,
    archimate_motivation,
    archimate_strategy,
    archimate_business,
    archimate_application,
    archimate_technology,
    archimate_implementation,
    archimate_layered,
    c4_system_landscape,
    c4_system_context,
    c4_container,
    c4_component,
    c4_deployment,
    matrix,
    control_structure,
    uca_matrix,
    fmea_matrix,
    bowtie,
    gsn,
)


def register_default_diagram_types(
    registry: ModuleRegistry,
    *,
    overrides: dict[str, dict[str, object]] | None = None,
    registered_names: set[str] | None = None,
) -> None:
    """Register the built-in diagram types on *registry*.

    When *overrides* and *registered_names* are supplied, each diagram type is
    checked via ``is_module_enabled`` before registration (fail-closed on
    unsatisfied requires).  Without them, all types are registered unconditionally
    (backward-compatible default).
    """
    effective_overrides = overrides or {}
    effective_registered = registered_names if registered_names is not None else set()
    for module in DEFAULT_DIAGRAM_KINDS:
        if overrides is None or is_module_enabled(module, effective_overrides, effective_registered):
            registry.register_diagram_type(module)
            effective_registered.add(str(module.name))
