"""Respell the confidential store's architecture references to their current titles.

An assurance node's reference holds the architecture artifact's *full* id. A rename now announces
itself and a follower retargets the stored refs, but a store written before that carries references
spelled with names their artifacts dropped — in front of a reader reviewing a safety argument, where
the name is all they see. Nothing fails: identity is the stem, and every consumer resolves through
it, so the drift is invisible to the product and permanent without a step.

The store cannot find the current spelling itself — it holds one-way references into architecture by
design (ADR@1783406789) and never reads the repository. So the index is handed in, built by the CLI
from the repo roots it is already upgrading, and a run with no repository root simply migrates
nothing here rather than guessing.

Which refs a rename speaks about is the same domain rule the live follower uses (`refs_to_retarget`),
keyed on the stem so a reference holding some third, older slug is healed too.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.deployment_upgrade.ports import (
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.domain.artifact_id import current_spelling_of
from src.domain.assurance.arch_ref_identity import refs_to_retarget
from src.domain.repository.operational_upgrade import TargetKind
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding

_DISTINCT_REFS = "SELECT DISTINCT arch_artifact_id FROM arch_refs"


class AssuranceArchRefRespellStep:
    id = "assurance-arch-ref-respell"
    version = 1
    kind: TargetKind = "assurance_sqlcipher"
    description = "Respell stored architecture references naming an artifact by a former slug"

    def __init__(self, canonical_entity_ids: Mapping[str, set[str]] | None = None) -> None:
        self._canonical = dict(canonical_entity_ids or {})

    def _respellings(self, view: OperationalTargetView) -> dict[str, str]:
        """Stored spelling → current spelling, for every distinct reference the store holds."""
        if not self._canonical:
            return {}
        respellings: dict[str, str] = {}
        for value in view.query_column(_DISTINCT_REFS):
            current = current_spelling_of(str(value), self._canonical)
            if current is not None:
                respellings[str(value)] = current
        return respellings

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        respellings = self._respellings(view)
        if not respellings:
            return []
        plural = "" if len(respellings) == 1 else "s"
        named = ", ".join(f"{stale} -> {current}" for stale, current in sorted(respellings.items())[:3])
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id=f"stale-arch-ref-slug:{view.target.stable_id}",
                location="arch_refs",
                description=f"{len(respellings)} architecture reference{plural} name an artifact by a former slug",
                severity="warning",
                auto_migratable=True,
                rewrite_summary=f"respell {len(respellings)} reference{plural} ({named})",
            )
        ]

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        respellings = self._respellings(view)
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            if not respellings:
                outcomes.append(AppliedFinding(finding=finding, outcome="skipped", detail="already current"))
                continue
            for stale, current in respellings.items():
                # `refs_to_retarget` decides which rows a spelling speaks about — the same rule the
                # live rename follower uses. A row already at the current spelling is left alone, so
                # the composite primary key cannot collide with itself.
                for ref in refs_to_retarget([{"arch_artifact_id": stale}], new_arch_artifact_id=current):
                    uow.execute_sql(
                        "UPDATE OR IGNORE arch_refs SET arch_artifact_id = ? WHERE arch_artifact_id = ?",
                        (current, str(ref["arch_artifact_id"])),
                    )
                    # A node already holding the current spelling for the same ref_type keeps its
                    # row (with its `resolved_at`); the superseded duplicate is dropped rather than
                    # left behind as a second reference to one artifact.
                    uow.execute_sql("DELETE FROM arch_refs WHERE arch_artifact_id = ?", (stale,))
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes
