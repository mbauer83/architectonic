"""Bind every relation a diagram body draws that its model records, so the picture and its bindings agree.

An ArchiMate diagram's ``connection-ids-used`` is what the reconcile treats as authoritative, and the
verifier refuses a body that draws a model relation the list does not name (E316) — by an arrow, or by
nesting one element inside the other. Until 0.11.2 neither the verifier nor the write path looked at
an ArchiMate diagram that carried any statement in ``diagram-entities`` (an occurrence, a label): such
a diagram was read as standalone, its body was never reconciled into its bindings, and the rule that
would have reported the gap was off. Diagrams written then hold nestings and arrows their lists never
named, and since the rule applies to them they fail verification without anyone having touched them.

This step lists those relations, as the reconcile would have listed them had it run. **It does not
guess.** A drawn pair whose model records exactly one connection that fits — any connection between
the two, or the one of the type an arrow states — has it added. A pair two connections fit is reported
for a person to settle, with the candidates named, and left as it is; a pair none fits is left too,
because a drawing without a model relation is the verifier's to judge, not a binding to make.

Which element an alias stands for and which connections fit a drawing are read exactly as E316 reads
them (`verification.drawn_relations`), over the repository's own model (`view.registry`): an alias only
an element's display alias resolves is bound here as the verifier resolves it, so what this step leaves
listed is what the rule then accepts.

Only the ``connection-ids-used`` block is rewritten, and only by adding to it. Applying the step twice
changes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.application.modeling.diagram_identities import strings_of
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._diagram_files import diagram_files, diagram_frontmatter
from src.application.repository_upgrade.steps._frontmatter_blocks import with_block
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.drawn_relations import diagram_body_is_reconcile_owned, drawn_relations
from src.domain.repository.frontmatter import Frontmatter, read_frontmatter, replace_frontmatter_text
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_CONNECTION_IDS_USED = "connection-ids-used"

@dataclass(frozen=True)
class _Binding:
    """What becomes of one diagram's drawn-but-unlisted relations."""

    #: Connection ids to add, in the order the body draws them.
    settled: tuple[str, ...] = ()
    #: A drawn relation's ends, and the connections that fit it — several.
    unsettled: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def _binding(content: str, frontmatter: Mapping[str, object], registry: ArtifactRegistry,
             stereotype_map: Mapping[str, str]) -> _Binding:
    """Each drawn relation the list does not name: settled where exactly one model connection fits it."""
    settled: dict[str, None] = {}
    unsettled: dict[str, tuple[str, ...]] = {}
    for drawn in drawn_relations(content, frontmatter, registry, stereotype_map):
        if drawn.listed or not drawn.fitting or any(connection_id in settled for connection_id in drawn.fitting):
            continue
        if len(drawn.fitting) == 1:
            settled[drawn.fitting[0]] = None
        else:
            unsettled[f"{drawn.relation.source_alias} -> {drawn.relation.target_alias}"] = drawn.fitting
    return _Binding(tuple(settled), unsettled)


class DrawnRelationsBoundStep:
    id = "d14-drawn-relations-bound"
    version = 1
    description = "List in connection-ids-used each model relation a diagram body draws and does not list"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        catalogs, registry = view.catalogs, view.registry
        findings: list[UpgradeFinding] = []
        for diagram in diagram_files(view):
            binding = self._binding_of(diagram.content, diagram.frontmatter, registry, catalogs)
            if binding.settled:
                count = len(binding.settled)
                plural = "" if count == 1 else "s"
                findings.append(UpgradeFinding(
                    step_id=self.id, finding_id=f"drawn-relation-unlisted:{diagram.location}",
                    location=diagram.location,
                    description=f"the body draws {count} model relation{plural} connection-ids-used does not list",
                    severity="warning", auto_migratable=True,
                    rewrite_summary=f"list {count} drawn relation{plural} ({', '.join(list(binding.settled)[:2])})",
                ))
            findings.extend(
                UpgradeFinding(
                    step_id=self.id, finding_id=f"drawn-relation-not-settled:{diagram.location}:{ends}",
                    location=diagram.location,
                    description=f"the body draws '{ends}', which {len(fitting)} model relations fit",
                    severity="warning", auto_migratable=False,
                    manual_instructions=(
                        "List the one this drawing shows with artifact_edit_diagram(connection_ids=…): "
                        + " | ".join(fitting)
                    ),
                )
                for ends, fitting in binding.unsettled.items()
            )
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        catalogs, registry = view.catalogs, view.registry
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            updated = self._rewritten(content, registry, catalogs) if content is not None else None
            if updated is None:
                outcomes.append(
                    AppliedFinding(finding=finding, outcome="error", detail="file no longer holds a diagram")
                )
            elif updated == content:
                outcomes.append(AppliedFinding(finding=finding, outcome="skipped", detail="already current"))
            else:
                writer.write_text(finding.location, updated)
                outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes

    def _binding_of(self, content: str, frontmatter: Mapping[str, object], registry: ArtifactRegistry,
                    catalogs: RuntimeCatalogs) -> _Binding:
        if not diagram_body_is_reconcile_owned(frontmatter, catalogs.diagram_types):
            return _Binding()
        return _binding(content, frontmatter, registry, catalogs.ontology.archimate_stereotype_to_connection_type())

    def _rewritten(self, content: str, registry: ArtifactRegistry, catalogs: RuntimeCatalogs) -> str | None:
        frontmatter = diagram_frontmatter(content)
        reading = read_frontmatter(content)
        if frontmatter is None or not isinstance(reading, Frontmatter):
            return None
        settled = self._binding_of(content, frontmatter, registry, catalogs).settled
        if not settled:
            return content
        listed = strings_of(frontmatter.get(_CONNECTION_IDS_USED))
        # A diagram stating no list yet gains an empty one first, so the block is written one way.
        text = (
            reading.text if _CONNECTION_IDS_USED in frontmatter
            else f"{reading.text.rstrip()}\n{_CONNECTION_IDS_USED}: []"
        )
        return replace_frontmatter_text(content, with_block(text, _CONNECTION_IDS_USED, [*listed, *settled]))
