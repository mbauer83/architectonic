"""Every place the GUI inserts markup as HTML is named here, with what makes its markup safe.

`v-html` hands a string to the browser's HTML parser. The GUI does that with repository content —
markdown, rendered diagrams — that any author can write, so each sink must either sanitise (DOMPurify,
directly or through `renderMarkdown`, `renderMatrixMarkdown` or `sanitizeDiagramSvg`) or render
markup the GUI generates itself from a checked-in table. The content security policy is the second
line; this register is the first, and a new sink fails it until somebody has said which case it is.

Shrink-or-justify: adding a row is the audit.
"""

from __future__ import annotations

import re

from tests.support.source_paths import REPO_ROOT

_GUI_SOURCE = REPO_ROOT / "tools" / "gui" / "src"

#: (file relative to tools/gui/src, the bound expression) → where its markup comes from.
AUDITED_SINKS: dict[tuple[str, str], str] = {
    ("ui/views/EditDiagramView.vue", "svgHtml"): "sanitizeDiagramSvg over the rendered SVG",
    ("ui/views/ViewpointDiagramView.vue", "svgHtml"): "sanitizeDiagramSvg over the rendered SVG",
    ("ui/views/DiagramDetailView.vue", "svgHtml"): "useDiagramReadingLens: sanitizeDiagramSvg",
    ("ui/views/EditMatrixView.vue", "previewHtml"): "renderMatrixMarkdown: DOMPurify",
    ("ui/views/CreateMatrixView.vue", "previewHtml"): "renderMatrixMarkdown: DOMPurify",
    ("ui/components/DiagramMatrixView.vue", "html"): "matrixHtmlOf(..., renderMatrixMarkdown): DOMPurify",
    ("ui/views/DocumentDetailView.vue", "previewHtml"): "renderMarkdown: DOMPurify",
    ("ui/components/MarkdownEditor.vue", "previewHtml"): "DOMPurify.sanitize over marked",
    ("ui/views/EntityDetailView.vue", "detail.content_html"): "HttpModelRepository: parseMarkdown",
    ("ui/components/DiagramEntitySidebar.vue", "selectedEntityDetailHtml"): "parseMarkdown, heading removed",
    ("ui/components/SidebarEntityEditor.vue", "contentHtml"): "DiagramEntitySidebar's sanitised HTML",
    ("ui/components/GraphNodeDetails.vue", "contentHtml"): "parseMarkdown, heading removed",
    ("ui/views/AssuranceGsnWizardView.vue", "sanitizedSvg"): "DOMPurify.sanitize, SVG profile",
    ("ui/components/AssuranceDiagramPanel.vue", "sanitizedSvg"): "DOMPurify.sanitize, SVG profile",
    ("ui/components/ArchimateTypeGlyph.vue", "markup"): "glyphKey: checked-in glyph table",
    ("ui/components/ScratchpadNote.vue", "glyph"): "glyphKey: checked-in glyph table",
    ("ui/components/GraphCanvasNode.vue", "visual.glyph"): "glyphKey: checked-in glyph table",
}

_SINK = re.compile(r'\bv-html="([^"]+)"')


def _sinks() -> set[tuple[str, str]]:
    return {
        (str(path.relative_to(_GUI_SOURCE)), match.group(1).strip())
        for path in _GUI_SOURCE.rglob("*.vue")
        if "__tests__" not in path.parts
        for match in _SINK.finditer(path.read_text(encoding="utf-8"))
    }


def test_every_html_sink_is_audited() -> None:
    unaudited = _sinks() - AUDITED_SINKS.keys()

    assert unaudited == set(), (
        "these insert markup as HTML and nobody has said what makes it safe. Sanitise it "
        "(DOMPurify, renderMarkdown, sanitizeDiagramSvg) or render it from a checked-in table, then "
        f"add a row naming which: {sorted(unaudited)}"
    )


def test_no_row_outlives_its_sink() -> None:
    assert AUDITED_SINKS.keys() - _sinks() == set()
