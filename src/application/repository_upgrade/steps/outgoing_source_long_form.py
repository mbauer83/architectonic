"""Spell a connection file's `source-entity` with its slug, as the file's schema requires.

A connection file names the entity whose outgoing connections it records, in the long form
``PREFIX@epoch.random.slug`` — the shipped frontmatter schema says so, and the verifier reports a short
one (W041). Editing, re-associating or removing one connection rewrote the whole file with the source
spelled as the caller had named it, and the REST surface names it by the short form it reads off a
connection id, so a file written correctly by its first connection was re-spelled short by any later
edit. The write path now spells it from the model; this step does the same for files already written.

The short form resolves to the right entity everywhere — identity is the stem — so nothing reads it
wrongly; it is respelled because the schema refuses it. **Only where the stem names exactly one
artifact** in the repository: with none or several there is no single long form to write, and the file
is left for the verifier to report. Only that one line changes.
"""

from __future__ import annotations

from src.application.repository_upgrade.canonical_ids import canonical_index
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._frontmatter_blocks import with_block
from src.application.repository_upgrade.steps._model_connections import connection_files, recorded_source
from src.domain.artifact_id import is_entity_id, slug_of, stable_id
from src.domain.repository.frontmatter import Frontmatter, read_frontmatter, replace_frontmatter_text
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_SOURCE_ENTITY = "source-entity"


def _long_form(source: str, canonical: dict[str, set[str]]) -> str | None:
    """The long form of a short *source*, when the repository names exactly one; else None."""
    if not is_entity_id(source) or slug_of(source) is not None:
        return None
    candidates = canonical.get(stable_id(source), set())
    return next(iter(candidates)) if len(candidates) == 1 else None


class OutgoingSourceLongFormStep:
    id = "d15-outgoing-source-entity-long-form"
    version = 1
    description = "Spell a connection file's source-entity in the long form its schema requires"
    scanned_surface: ScannedSurface = "connection_declarations"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        canonical = canonical_index([view])
        findings: list[UpgradeFinding] = []
        for location in connection_files(view):
            content = view.read_text(location)
            source = recorded_source(content) if content is not None else ""
            if (long_form := _long_form(source, canonical)) is None:
                continue
            findings.append(UpgradeFinding(
                step_id=self.id, finding_id=f"short-source-entity:{location}", location=location,
                description=f"source-entity '{source}' is the short form the connection schema refuses",
                severity="warning", auto_migratable=True,
                rewrite_summary=f"respell source-entity as {long_form}",
            ))
        return findings

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        canonical = canonical_index([view])
        outcomes: list[AppliedFinding] = []
        for finding in findings:
            content = view.read_text(finding.location)
            reading = read_frontmatter(content) if content is not None else None
            if content is None or not isinstance(reading, Frontmatter):
                outcomes.append(AppliedFinding(finding=finding, outcome="error", detail="file no longer exists"))
                continue
            long_form = _long_form(recorded_source(content), canonical)
            if long_form is None:
                outcomes.append(AppliedFinding(finding=finding, outcome="skipped", detail="already current"))
                continue
            writer.write_text(
                finding.location, replace_frontmatter_text(content, with_block(reading.text, _SOURCE_ENTITY, long_form))
            )
            outcomes.append(AppliedFinding(finding=finding, outcome="applied"))
        return outcomes
