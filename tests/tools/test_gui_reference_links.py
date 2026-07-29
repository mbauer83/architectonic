from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_node(expr: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", expr],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_build_reference_markdown_uses_relative_path_for_existing_document() -> None:
    output = _run_node(
        """
        import { buildReferenceMarkdown } from './tools/gui/src/ui/lib/referenceLinks.js'
        const value = buildReferenceMarkdown({
          currentPath: '/tmp/ws/engagements/ENG/architecture-repository/documents/adr/ADR@1.a.current.md',
          targetPath: '/tmp/ws/engagements/ENG/architecture-repository/model/application/components/APP@2.b.target.md',
          title: 'Target Component',
        })
        console.log(value)
        """,
    )
    assert output == "[Target Component](../../model/application/components/APP@2.b.target.md)"


def test_build_reference_markdown_uses_relative_path_for_new_document_draft() -> None:
    output = _run_node(
        """
        import { buildReferenceMarkdown, draftDocumentPath } from './tools/gui/src/ui/lib/referenceLinks.js'
        const value = buildReferenceMarkdown({
          currentPath: draftDocumentPath('adr', 'decisions/adr'),
          targetPath: '/tmp/ws/engagements/ENG/architecture-repository/documents/spec/SPE@2.b.target.md',
          title: 'Target Spec',
          section: 'Decision',
        })
        console.log(value)
        """,
    )
    assert output == "[Target Spec - Decision](../../spec/SPE@2.b.target.md#decision)"


def test_draft_document_path_uses_configured_subdirectory() -> None:
    output = _run_node(
        """
        import { draftDocumentPath } from './tools/gui/src/ui/lib/referenceLinks.js'
        console.log(draftDocumentPath('adr', 'decisions/adr'))
        """,
    )
    assert output == "documents/decisions/adr/__draft__.md"


def test_repo_relative_normalization_strips_absolute_prefix() -> None:
    output = _run_node(
        """
        import { toRepoRelativePath } from './tools/gui/src/ui/lib/referenceLinks.js'
        console.log(JSON.stringify([
          toRepoRelativePath('/tmp/ws/engagements/ENG/architecture-repository/documents/adr/a.md'),
          toRepoRelativePath('/tmp/ws/engagements/ENG/architecture-repository/diagram-catalog/diagrams/d.puml'),
          toRepoRelativePath('/tmp/ws/engagements/ENG/architecture-repository/model/technology/nodes/n.md'),
        ]))
        """,
    )
    assert json.loads(output) == [
        "documents/adr/a.md",
        "diagram-catalog/diagrams/d.puml",
        "model/technology/nodes/n.md",
    ]


def test_to_gui_artifact_href_rewrites_matrix_entity_link() -> None:
    output = _run_node(
        """
        import { toGuiArtifactHref } from './tools/gui/src/ui/lib/referenceLinks.js'
        console.log(toGuiArtifactHref('../../model/motivation/outcomes/OUT@1712870400.LrpdG0.increased-architectural-coherence.md'))
        """,
    )
    assert output == "/entity?id=OUT@1712870400.LrpdG0.increased-architectural-coherence"


def test_to_gui_artifact_href_preserves_document_anchor() -> None:
    output = _run_node(
        """
        import { toGuiArtifactHref } from './tools/gui/src/ui/lib/referenceLinks.js'
        console.log(toGuiArtifactHref('../../documents/adr/ADR@1712870400.AbCdE1.record.md#decision'))
        """,
    )
    assert output == "/document?id=ADR@1712870400.AbCdE1.record#decision"
