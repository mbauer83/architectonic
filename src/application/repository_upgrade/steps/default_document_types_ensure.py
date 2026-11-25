"""Detector/migrator for the shipped base document types.

A repository created before a document type shipped never receives it: the workspace template
writes `.arch-repo/documents/` once, at creation, and `default-schemata-ensure` covers only
`.arch-repo/schemata/`. So a repository from before 0.12.0 had no `stress-analysis` type and
could not start a stress analysis. This step adds every shipped base document type that is
missing, in the template's byte format.

An existing file is never read for differences, let alone overwritten: document types are
meant to be adapted per repository (sections, suggested connections, frontmatter), so a
difference from the shipped default is the ordinary state, not a finding.
"""

from __future__ import annotations

import json

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS
from src.domain.repository.repo_layout import ARCH_DOC_SCHEMATA, ARCH_REPO
from src.domain.repository.repository_upgrade import AppliedFinding, ScannedSurface, UpgradeFinding

_DOCUMENTS_DIR = f"{ARCH_REPO}/{ARCH_DOC_SCHEMATA}"


class DefaultDocumentTypesEnsureStep:
    id = "default-document-types-ensure"
    version = 1
    description = "Add missing shipped document types (never overwriting existing ones)"
    scanned_surface: ScannedSurface = "profiles"

    def detect(self, view: RepoUpgradeView) -> list[UpgradeFinding]:
        return [
            UpgradeFinding(
                step_id=self.id,
                finding_id=f"missing-document-type:{doc_type}",
                location=f"{_DOCUMENTS_DIR}/{doc_type}.json",
                description=f"the shipped document type {doc_type} is absent",
                severity="info",
                auto_migratable=True,
                rewrite_summary=f"add the shipped document type {doc_type}",
            )
            for doc_type in BASE_DOCUMENT_SCHEMAS
            if view.read_text(f"{_DOCUMENTS_DIR}/{doc_type}.json") is None
        ]

    def apply(
        self,
        view: RepoUpgradeView,
        writer: RepoUpgradeWriter,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        results: list[AppliedFinding] = []
        for finding in findings:
            doc_type = finding.location.rsplit("/", 1)[-1].removesuffix(".json")
            payload = BASE_DOCUMENT_SCHEMAS.get(doc_type)
            if payload is None or view.read_text(finding.location) is not None:
                results.append(AppliedFinding(finding=finding, outcome="skipped", detail="already present"))
                continue
            writer.write_text(finding.location, json.dumps(payload, indent=2) + "\n")
            results.append(AppliedFinding(finding=finding, outcome="applied"))
        return results
