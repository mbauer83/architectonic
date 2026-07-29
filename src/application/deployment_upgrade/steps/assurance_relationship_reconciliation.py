"""Operational migration for the reconciled assurance relationship model.

Older stores carry the pre-reconciliation vocabulary. Deterministic repairs:
`violates` UCA→hazard edges become `leads-to` (deleted when a parallel
`leads-to` already exists); `accountable-to` edges flip direction and retype —
`responsible-for` when the old source is an assurance-constraint,
`accountable-for` when it is a risk; the `evidenced-by` and `refines`
architecture-reference types are renamed to their collision-free catalog names.
Vocabulary with no deterministic semantics (`satisfied-by`, `responsible-of`,
`accountable-to` between other node types) is reported as a manual finding —
never silently rewritten.
"""

from __future__ import annotations

from src.application.deployment_upgrade.ports import (
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.domain.repository.operational_upgrade import TargetKind
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding

_EDGES = "assurance_edges"
_NODES = "assurance_nodes"

_COUNT_VIOLATES = f"SELECT count(*) FROM {_EDGES} WHERE conn_type = 'violates'"
_COUNT_FLIPPABLE = f"""
    SELECT count(*) FROM {_EDGES}
    WHERE conn_type = 'accountable-to' AND source_id IN (
        SELECT node_id FROM {_NODES} WHERE node_type IN ('assurance-constraint', 'risk')
    )
"""
_COUNT_MANUAL_EDGES = f"""
    SELECT count(*) FROM {_EDGES}
    WHERE conn_type IN ('satisfied-by', 'responsible-of')
       OR (conn_type = 'accountable-to' AND source_id NOT IN (
            SELECT node_id FROM {_NODES} WHERE node_type IN ('assurance-constraint', 'risk')))
"""
_COUNT_LEGACY_REFS = (
    "SELECT count(*) FROM arch_refs WHERE ref_type IN ('evidenced-by', 'refines')"
)


def _count(view: OperationalTargetView, sql: str) -> int:
    value = view.query_scalar(sql)
    return int(value) if isinstance(value, (int, float, str)) else 0


class AssuranceRelationshipReconciliationStep:
    id = "assurance-0001-stpa-relationship-reconciliation"
    version = 1
    kind: TargetKind = "assurance_sqlcipher"
    description = "Reconcile pre-handbook assurance relationship vocabulary"

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        location = view.target.display_location
        violates = _count(view, _COUNT_VIOLATES)
        if violates:
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id="violates-edges",
                    location=location,
                    description=f"{violates} 'violates' edge(s) predate the leads-to vocabulary",
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary="retype to leads-to (drop duplicates of existing leads-to edges)",
                )
            )
        flippable = _count(view, _COUNT_FLIPPABLE)
        if flippable:
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id="accountable-to-edges",
                    location=location,
                    description=(
                        f"{flippable} 'accountable-to' edge(s) predate the "
                        "responsible-for/accountable-for vocabulary"
                    ),
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary=(
                        "flip direction; retype constraint-sourced edges to responsible-for "
                        "and risk-sourced edges to accountable-for"
                    ),
                )
            )
        manual = _count(view, _COUNT_MANUAL_EDGES)
        if manual:
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id="undecidable-legacy-edges",
                    location=location,
                    description=(
                        f"{manual} legacy edge(s) (satisfied-by / responsible-of / other "
                        "accountable-to) have no deterministic replacement"
                    ),
                    severity="warning",
                    auto_migratable=False,
                    manual_instructions=(
                        "Review each edge and re-author it in the reconciled vocabulary "
                        "(responsible-for, accountable-for, refines) or delete it; the "
                        "migration never guesses semantics."
                    ),
                )
            )
        refs = _count(view, _COUNT_LEGACY_REFS)
        if refs:
            findings.append(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id="legacy-reference-types",
                    location=location,
                    description=(
                        f"{refs} architecture reference(s) use the pre-catalog ref types "
                        "('evidenced-by', 'refines')"
                    ),
                    severity="warning",
                    auto_migratable=True,
                    rewrite_summary=(
                        "rename ref types: evidenced-by → evidenced-by-artifact, "
                        "refines → refines-requirement"
                    ),
                )
            )
        return findings

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        ids = {f.finding_id for f in findings}
        if "violates-edges" in ids:
            uow.execute_sql(
                f"""DELETE FROM {_EDGES} WHERE conn_type = 'violates' AND EXISTS (
                        SELECT 1 FROM {_EDGES} AS existing
                        WHERE existing.source_id = {_EDGES}.source_id
                          AND existing.target_id = {_EDGES}.target_id
                          AND existing.conn_type = 'leads-to')"""
            )
            uow.execute_sql(f"UPDATE {_EDGES} SET conn_type = 'leads-to' WHERE conn_type = 'violates'")
        if "accountable-to-edges" in ids:
            for node_type, new_type in (
                ("assurance-constraint", "responsible-for"),
                ("risk", "accountable-for"),
            ):
                uow.execute_sql(
                    f"""UPDATE {_EDGES}
                        SET source_id = target_id, target_id = source_id, conn_type = ?
                        WHERE conn_type = 'accountable-to' AND source_id IN (
                            SELECT node_id FROM {_NODES} WHERE node_type = ?)""",
                    (new_type, node_type),
                )
        if "legacy-reference-types" in ids:
            uow.execute_sql(
                "UPDATE arch_refs SET ref_type = 'evidenced-by-artifact' WHERE ref_type = 'evidenced-by'"
            )
            uow.execute_sql(
                "UPDATE arch_refs SET ref_type = 'refines-requirement' WHERE ref_type = 'refines'"
            )
        return [
            AppliedFinding(finding=f, outcome="applied")
            for f in findings
            if f.auto_migratable
        ]
