"""Detector/migrator for the shipped document types.

A repository created before a document type shipped never receives it: the workspace template
writes `.arch-repo/documents/` once, at creation, and `default-schemata-ensure` covers only
`.arch-repo/schemata/`. So a repository from before 0.12.0 had no `stress-analysis` type and
could not start a stress analysis. This step adds every shipped document type that is missing —
the base and the assurance set, the scope the template writes at creation — through the same owner
the template writes them with (`shipped_defaults`).

An existing file is never read for differences, let alone overwritten: document types are
meant to be adapted per repository (sections, suggested connections, frontmatter), so a
difference from the shipped default is the ordinary state, not a finding.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.steps._shipped_files import (
    apply_missing_shipped,
    missing_shipped_findings,
)
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding
from src.domain.repository.shipped_defaults import shipped_document_types


class DefaultDocumentTypesEnsureStep:
    id = "default-document-types-ensure"
    version = 1
    description = "Add missing shipped document types (never overwriting existing ones)"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        return missing_shipped_findings(
            self.id, shipped_document_types(), view,
            finding_prefix="missing-document-type", what="the shipped document type",
        )

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        return apply_missing_shipped(shipped_document_types(), view, writer, findings)
