"""One batched read of everything the failure-mode rules need, plus the derivation pass.

Separated from the verifier so that adding a rule which needs a factor, a digest, or the element a
node binds to does not add a query: the read happens once for the whole store and every rule is
handed the result. Keeping it here also keeps the verifier's own body a list of checks, which is
what a reader goes to that file for.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.assurance_fmea_architecture import ArchitectureBasis
from src.application.assurance_fmea_occurrence_evidence import ElementSecurityBasis
from src.application.assurance_ports import ConfidentialAssuranceStore
from src.application.verification import _assurance_rules_failure_modes as failures
from src.application.verification._assurance_model_join import bound_elements, occurrence_basis
from src.application.verification.assurance_two_way_coverage import SEVERE_LOSS_VALUES

if TYPE_CHECKING:
    from src.domain.assurance.fmea_factors import FactorAssessment

def read_failure_mode_context(
    store: ConfidentialAssuranceStore,
    all_nodes: list[dict[str, object]],
    all_edges: list[dict[str, object]],
    *,
    basis: ArchitectureBasis,
    security: Mapping[str, ElementSecurityBasis],
) -> "FailureModeContext":
    """One batched read and one derivation pass for every failure-mode rule that needs them."""
    from src.application.assurance_fmea_derivation import derive_factors  # noqa: PLC0415
    from src.domain.assurance.fmea_action_priority import action_priority  # noqa: PLC0415
    from src.domain.assurance.fmea_factors import (  # noqa: PLC0415
        DETECTABILITY,
        OCCURRENCE,
        SEVERITY,
        effective_factor,
    )

    ids = [str(n["node_id"]) for n in all_nodes if str(n.get("node_type", "")) == failures.FAILURE_MODE]
    nodes_by_id = {str(n["node_id"]): n for n in all_nodes}
    # Read before the early return: which element each node binds to is what tells the coverage pass
    # that an element has been looked at, and a store holding only a control structure — no failure
    # modes yet — is exactly the case where that pass has something to say.
    element_by_node = bound_elements(store)
    if not ids:
        return FailureModeContext({}, {}, {}, frozenset(), dict(element_by_node))
    assessments = store.read_fmea_assessments(ids)
    derived_severity: dict[str, str | None] = {}
    digests: dict[str, dict[str, str]] = {}
    priorities: dict[str, str] = {}
    for node_id in ids:
        derivation = derive_factors(
            node_id, nodes=all_nodes, edges=all_edges,
            occurrence_basis=occurrence_basis(
                nodes_by_id[node_id], element_by_node.get(node_id, ""),
                basis=basis, security=security,
            ),
        )
        derived_severity[node_id] = derivation.severity.value
        digests[node_id] = dict(derivation.digests)
        rows = _as_assessments(assessments.get(node_id, []))
        priorities[node_id] = action_priority(
            effective_factor(
                SEVERITY, assessments=[a for a in rows if a.factor == SEVERITY],
                derived_value=derivation.severity.value,
                current_basis_digest=derivation.digests["severity"],
            ).value,
            effective_factor(
                OCCURRENCE, assessments=[a for a in rows if a.factor == OCCURRENCE],
                derived_value=None,
                current_basis_digest=derivation.digests["occurrence"],
            ).value,
            effective_factor(
                DETECTABILITY, assessments=[a for a in rows if a.factor == DETECTABILITY],
                derived_value=derivation.detectability.value,
                current_basis_digest=derivation.digests["detectability"],
            ).value,
        )
    return FailureModeContext(
        assessments={k: list(v) for k, v in assessments.items()},
        derived_severity=derived_severity,
        digests=digests,
        high_priority_ids=failures.high_priority_ids(priorities),
        element_by_node=dict(element_by_node),
    )


def _as_assessments(rows: list[dict[str, object]]) -> list["FactorAssessment"]:
    from src.domain.assurance.fmea_factors import FactorAssessment  # noqa: PLC0415

    return [
        FactorAssessment(
            node_id=str(row.get("node_id") or ""),
            factor=str(row.get("factor") or ""),
            basis_digest=str(row.get("basis_digest") or ""),
            revision=int(str(row.get("revision") or 0)),
            value=str(row.get("value") or ""),
            justification=str(row.get("justification") or ""),
            author=str(row.get("author") or ""),
            created_at=str(row.get("created_at") or ""),
        )
        for row in rows
    ]


@dataclass(frozen=True)
class FailureModeContext:
    assessments: dict[str, list[dict[str, object]]]
    derived_severity: dict[str, str | None]
    digests: dict[str, dict[str, str]]
    high_priority_ids: frozenset[str]
    element_by_node: dict[str, str]

    @property
    def severity_by_element(self) -> dict[str, str]:
        """The worst derived severity reaching each element, for the data-classification check.

        Keyed by element rather than by failure mode because the question is about the data an
        element touches, and several of its failure modes may reach a loss of differing severity.
        """
        worst: dict[str, str] = {}
        for node_id, severity in self.derived_severity.items():
            element = self.element_by_node.get(node_id, "")
            if not element or severity is None:
                continue
            if severity in SEVERE_LOSS_VALUES or element not in worst:
                worst[element] = severity
        return worst


