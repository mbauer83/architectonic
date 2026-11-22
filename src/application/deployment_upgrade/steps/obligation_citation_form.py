"""Bring a store's obligation citations to `source` and `provision`.

An obligation says which rule it comes from in two attributes. Stores written before hold the
citation as the wizard used to write it (`scheme`, `code`), as obligations were written by hand
(`framework`, `clause`), or as the ontology text used to ask for it (`cites`, a single
`source:provision`), and nothing reads any of them — so the citation is on the
record and invisible to every check. What moves, and what cannot, is decided by the domain module
that names the attributes; this step finds the obligations and writes the result.

Each rewritten obligation gets an entry in the store's audit archive, in the same transaction as
the rewrite. The entry names the attributes that moved and never their values: the archive records
that a record changed, and the citation itself stays in the record.
"""

from __future__ import annotations

import json

from src.application.assurance.node_attributes import attributes_of
from src.application.deployment_upgrade.ports import (
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.domain.assurance.obligation_citation import (
    PROVISION,
    SOURCE,
    SUPERSEDED_ATTRIBUTES,
    CitationRewrite,
    rewrite_superseded,
)
from src.domain.repository.operational_upgrade import TargetKind
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding

#: Narrowed in SQL to the rows that can hold a former attribute, so a store already in the current
#: form is one query that returns nothing. The match is on the quoted key and may admit a row whose
#: *value* happens to contain it; the rewrite then finds nothing to move and the row is not reported.
_CANDIDATES = (
    "SELECT node_id FROM assurance_nodes WHERE node_type = 'obligation' AND ("
    + " OR ".join("attributes_json LIKE ?" for _ in SUPERSEDED_ATTRIBUTES)
    + ") ORDER BY node_id"
)
_CANDIDATE_PATTERNS = tuple(f'%"{name}"%' for name in SUPERSEDED_ATTRIBUTES)
_ATTRIBUTES_OF = "SELECT attributes_json FROM assurance_nodes WHERE node_id = ?"
_WRITE_ATTRIBUTES = "UPDATE assurance_nodes SET attributes_json = ? WHERE node_id = ?"

_MOVABLE = "superseded-citation"
_UNMOVABLE = "unmovable-citation"
#: The archive's operation for a changed record — the one an ordinary edit records.
_AUDIT_OPERATION = "UPDATE"


def _moves(rewrite: CitationRewrite) -> str:
    return ", ".join(f"{former} -> {current}" for former, current in rewrite.moved)


class ObligationCitationFormStep:
    id = "assurance-obligation-citation-form"
    version = 1
    kind: TargetKind = "assurance_sqlcipher"
    description = "Move obligation citations from scheme/code, framework/clause or cites to source and provision"

    def _rewrites(self, view: OperationalTargetView) -> dict[str, CitationRewrite]:
        """Obligation id → what bringing it to the current form does, for each one it concerns."""
        rewrites: dict[str, CitationRewrite] = {}
        for node_id in view.query_column(_CANDIDATES, _CANDIDATE_PATTERNS):
            blob = view.query_scalar(_ATTRIBUTES_OF, (node_id,))
            rewrite = rewrite_superseded(attributes_of({"attributes_json": blob}))
            if rewrite.moved or rewrite.left_in_place:
                rewrites[str(node_id)] = rewrite
        return rewrites

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        for node_id, rewrite in self._rewrites(view).items():
            if rewrite.changes_something:
                findings.append(
                    UpgradeFinding(
                        step_id=self.id,
                        finding_id=f"{_MOVABLE}:{node_id}",
                        location=node_id,
                        description="obligation holds its citation in attributes nothing reads",
                        severity="warning",
                        auto_migratable=True,
                        rewrite_summary=f"move {_moves(rewrite)}",
                    )
                )
            findings.extend(
                UpgradeFinding(
                    step_id=self.id,
                    finding_id=f"{_UNMOVABLE}:{node_id}:{former}",
                    location=node_id,
                    description=f"obligation's `{former}` was left in place: {reason}",
                    severity="warning",
                    auto_migratable=False,
                    manual_instructions=(
                        f"Edit the obligation: set `{SOURCE}` and `{PROVISION}` to what it cites, "
                        f"then remove `{former}`."
                    ),
                )
                for former, reason in rewrite.left_in_place
            )
        return findings

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        rewrites = self._rewrites(view)
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            if not finding.auto_migratable:
                continue
            rewrite = rewrites.get(finding.location)
            if rewrite is None or not rewrite.changes_something:
                outcomes.append(AppliedFinding(finding=finding, outcome="skipped", detail="already current"))
                continue
            uow.execute_sql(_WRITE_ATTRIBUTES, (json.dumps(rewrite.attributes), finding.location))
            uow.record_audit(
                _AUDIT_OPERATION,
                node_id=finding.location,
                payload={
                    "updated_fields": ["attributes"],
                    "upgrade_step": self.id,
                    "moved_attributes": [list(pair) for pair in rewrite.moved],
                },
            )
            outcomes.append(AppliedFinding(finding=finding, outcome="applied", detail=_moves(rewrite)))
        return outcomes
