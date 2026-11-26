"""Take statements about a diagram's instances out of the list of the model elements it draws.

``entity-ids-used`` names model elements. Until 0.11.2 the index also held every item under a diagram's
``diagram-entities`` as a record, whatever the diagram type declared, so an ArchiMate ``occurrence``
statement ("draw this element again") was an entity with an id of the held form
``DIAGRAM#occurrence/ALIAS``. Diagram writes of that time resolved a body's aliases against the index
and listed such ids beside the elements they draw again — sometimes another diagram's, where two
diagrams gave an occurrence the same alias.

A diagram type now states which of its keys hold records, and an occurrence is not one, so those ids
name nothing and the verifier refuses the diagram (E301). Nothing is lost by removing them: the
element an occurrence draws is listed under its own id, and the occurrence itself stays stated where it
always was, in ``diagram-entities`` and ``bindings``.

**Only what provably names no record is removed.** An entry goes when it is spelled as a held record
whose host diagram is in this repository and whose type does not hold records under that key. An entry
naming a host this repository does not hold, or a key its type does hold, is left for the verifier to
judge. Every other line of the file keeps its bytes, and applying the step twice changes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.application.modeling.diagram_identities import strings_of
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._diagram_files import diagram_files, diagram_frontmatter
from src.application.repository_upgrade.steps._frontmatter_blocks import with_block
from src.domain.artifact_id import read_held_record_id, stable_id
from src.domain.diagrams.diagram_type_field import diagram_type_of
from src.domain.modules.catalogs import DiagramTypeCatalog
from src.domain.repository.frontmatter import Frontmatter, read_frontmatter, replace_frontmatter_text
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_ENTITY_IDS_USED = "entity-ids-used"


def _diagram_types(view: RepoUpgradeView) -> dict[str, str]:
    """The diagram type of every diagram the repository holds, by the diagram's stable id."""
    return {
        stable_id(str(diagram.frontmatter.get("artifact-id", ""))): diagram_type_of(diagram.frontmatter)
        for diagram in diagram_files(view)
    }


def _names_no_record(entry: str, diagram_types: Mapping[str, str], catalog: DiagramTypeCatalog) -> bool:
    held = read_held_record_id(entry)
    if held is None:
        return False
    host_type = diagram_types.get(stable_id(held.diagram_id))
    module = catalog.find_diagram_type(host_type) if host_type is not None else None
    return module is not None and held.entity_type not in module.held_record_keys


def _statements_listed(
    frontmatter: Mapping[str, object], diagram_types: Mapping[str, str], catalog: DiagramTypeCatalog
) -> list[str]:
    return [
        entry for entry in strings_of(frontmatter.get(_ENTITY_IDS_USED))
        if _names_no_record(entry, diagram_types, catalog)
    ]


class EntityListNamesElementsStep:
    id = "d13-entity-ids-used-names-elements"
    version = 1
    description = "Remove statements about a diagram's instances from the elements it lists as drawn"
    scanned_surface: ScannedSurface = "diagram_frontmatter"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        diagram_types = _diagram_types(view)
        catalog = view.catalogs.diagram_types
        findings: list[UpgradeFinding] = []
        for diagram in diagram_files(view):
            listed = _statements_listed(diagram.frontmatter, diagram_types, catalog)
            if not listed:
                continue
            plural = "" if len(listed) == 1 else "s"
            findings.append(UpgradeFinding(
                step_id=self.id, finding_id=f"statement-listed-as-element:{diagram.location}",
                location=diagram.location,
                description=f"entity-ids-used lists {len(listed)} id{plural} of a statement, which names no element",
                severity="warning", auto_migratable=True,
                rewrite_summary=f"remove {len(listed)} statement id{plural} ({', '.join(sorted(set(listed))[:2])})",
            ))
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        diagram_types = _diagram_types(view)
        catalog = view.catalogs.diagram_types
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            updated = self._rewritten(content, diagram_types, catalog) if content is not None else None
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

    def _rewritten(self, content: str, diagram_types: Mapping[str, str], catalog: DiagramTypeCatalog) -> str | None:
        frontmatter = diagram_frontmatter(content)
        reading = read_frontmatter(content)
        if frontmatter is None or not isinstance(reading, Frontmatter):
            return None
        listed = set(_statements_listed(frontmatter, diagram_types, catalog))
        if not listed:
            return content
        kept = [entry for entry in strings_of(frontmatter.get(_ENTITY_IDS_USED)) if entry not in listed]
        return replace_frontmatter_text(content, with_block(reading.text, _ENTITY_IDS_USED, kept))
