"""`default-document-types-ensure`: a shipped document type a repository lacks is added; one it has,
in whatever form, is left alone.

Regression: a repository created before the stress-analysis type shipped never received it, because
only the workspace template wrote document types and only at creation, so such a repository could not
start a stress analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.repository_upgrade.steps.default_document_types_ensure import DefaultDocumentTypesEnsureStep
from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS
from src.domain.repository.repo_default_stress_analysis import STRESS_ANALYSIS
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeView, FilesystemRepoUpgradeWriter

_CUSTOM_ADR = '{"name": "Our own ADR", "custom": true}\n'


def _repo(tmp_path: Path, present: dict[str, str]) -> Path:
    documents = tmp_path / ".arch-repo" / "documents"
    documents.mkdir(parents=True)
    for doc_type, content in present.items():
        (documents / f"{doc_type}.json").write_text(content, encoding="utf-8")
    return tmp_path


def test_a_missing_type_is_found_and_a_present_one_is_not_whatever_it_holds(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"adr": _CUSTOM_ADR})

    findings = DefaultDocumentTypesEnsureStep().detect(FilesystemRepoUpgradeView(root))

    missing = {f.finding_id.removeprefix("missing-document-type:") for f in findings}
    assert STRESS_ANALYSIS in missing
    assert "adr" not in missing
    assert missing == set(BASE_DOCUMENT_SCHEMAS) - {"adr"}
    assert all(f.auto_migratable for f in findings)


def test_applying_writes_the_template_format_and_leaves_an_adapted_type_byte_for_byte(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"adr": _CUSTOM_ADR})
    step = DefaultDocumentTypesEnsureStep()
    view = FilesystemRepoUpgradeView(root)

    results = step.apply(view, FilesystemRepoUpgradeWriter(root), step.detect(view))

    assert {r.outcome for r in results} == {"applied"}
    written = (root / ".arch-repo" / "documents" / f"{STRESS_ANALYSIS}.json").read_text(encoding="utf-8")
    assert written == json.dumps(BASE_DOCUMENT_SCHEMAS[STRESS_ANALYSIS], indent=2) + "\n"
    assert (root / ".arch-repo" / "documents" / "adr.json").read_text(encoding="utf-8") == _CUSTOM_ADR
    assert step.detect(view) == []
