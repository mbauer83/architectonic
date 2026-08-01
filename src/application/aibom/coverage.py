"""AIBOM coverage evaluation.

The honest answer to "what is missing for a valid AIBOM" — per AI component: required
attributes the entity has not authored, missing dataset linkage, a missing governance edge,
and (repo-wide) derivation roles no connection type is bound to. Pure: it reads the already-
derived components plus the per-specialization required-attribute sets; no IO.

A gap is a *finding*, never an error or a silent omission — an AI component with no dataset
link still exports, it just reports the gap so the operator can act.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.application.aibom.derivation import AibomComponent
from src.domain.assurance.aibom_roles import DerivationRoleBindings


@dataclass(frozen=True)
class ComponentCoverage:
    """The coverage gaps for one AI component, in two tiers so a wizard can act sensibly on
    "optional or unavailable" information (PLAN Stream F): REQUIRED attributes and the
    dataset/governance links are *blocking* gaps (the AIBOM is under-documented without them);
    RECOMMENDED attributes are *advisory* — surfaced to help, never a validity blocker.
    Optional attributes are not tracked as gaps at all."""

    entity_id: str
    name: str
    specialization: str
    missing_required_attributes: tuple[str, ...] = ()
    missing_recommended_attributes: tuple[str, ...] = ()
    missing_dataset_linkage: bool = False
    missing_governance: bool = False

    @property
    def clean(self) -> bool:
        """No BLOCKING gap — the AIBOM is valid for this component. Advisory (recommended)
        gaps do not make it unclean; they are surfaced separately."""
        return not (self.missing_required_attributes or self.missing_dataset_linkage or self.missing_governance)

    @property
    def complete(self) -> bool:
        """Clean AND no advisory gaps — nothing more the operator could sensibly fill in."""
        return self.clean and not self.missing_recommended_attributes


@dataclass(frozen=True)
class AibomCoverage:
    """The repo-wide coverage report: per-component gaps plus roles nothing binds to."""

    components: tuple[ComponentCoverage, ...] = ()
    unbound_roles: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.unbound_roles and all(c.clean for c in self.components)


#: Specializations for which a missing dataset link is a genuine gap — a model/agent with no
#: data lineage is under-documented; a dataset or tool interface has no datasets of its own.
_EXPECTS_DATASETS: frozenset[str] = frozenset({"ai-model", "ai-agent"})
#: Specializations for which a missing governance edge is a gap (who is accountable).
_EXPECTS_GOVERNANCE: frozenset[str] = frozenset({"ai-model", "ai-agent", "ai-inference-service"})


def evaluate_coverage(
    components: Sequence[AibomComponent],
    required_attributes: Mapping[str, Sequence[str]],
    bindings: DerivationRoleBindings,
    *,
    recommended_attributes: Mapping[str, Sequence[str]] | None = None,
) -> AibomCoverage:
    """Per-component coverage plus the repo-wide unbound-role finding.

    ``required_attributes`` / ``recommended_attributes`` map a specialization slug → the
    attribute names its effective schema marks ``required`` / ``recommended`` (resolved by
    the caller from the schema; passed in to keep this pure). An attribute is *missing* when
    the component authored no value for it. Required-missing is blocking; recommended-missing
    is advisory."""
    recommended = recommended_attributes or {}
    reports = tuple(
        _component_coverage(
            component,
            tuple(required_attributes.get(component.specialization, ())),
            tuple(recommended.get(component.specialization, ())),
        )
        for component in components
    )
    return AibomCoverage(components=reports, unbound_roles=tuple(sorted(bindings.unbound_roles())))


def _component_coverage(
    component: AibomComponent, required: tuple[str, ...], recommended: tuple[str, ...]
) -> ComponentCoverage:
    authored_keys = set(component.authored)
    missing_required = tuple(name for name in required if name not in authored_keys)
    missing_recommended = tuple(name for name in recommended if name not in authored_keys)
    missing_datasets = component.specialization in _EXPECTS_DATASETS and not component.datasets
    missing_governance = component.specialization in _EXPECTS_GOVERNANCE and not component.governance
    return ComponentCoverage(
        entity_id=component.entity_id,
        name=component.name,
        specialization=component.specialization,
        missing_required_attributes=missing_required,
        missing_recommended_attributes=missing_recommended,
        missing_dataset_linkage=missing_datasets,
        missing_governance=missing_governance,
    )
