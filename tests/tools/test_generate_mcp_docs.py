from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.docs.mcp_docs import (
    GeneratedDocument,
    ToolInfo,
    generate_documents,
    render_arch_read_table,
    replace_regions,
    unknown_readme_mentions,
)


def test_replace_regions_updates_matching_marker_only() -> None:
    text = "A\n<!-- mcp-tools:begin arch-read -->\nold\n<!-- mcp-tools:end arch-read -->\nB\n"

    updated = replace_regions(text, {"arch-read": "new"})

    assert updated == "A\n<!-- mcp-tools:begin arch-read -->\nnew\n<!-- mcp-tools:end arch-read -->\nB\n"


def test_replace_regions_requires_marker() -> None:
    with pytest.raises(ValueError, match="Missing MCP docs marker"):
        replace_regions("plain text", {"arch-read": "table"})


def test_render_arch_read_table_uses_first_sentence_and_read_only_access() -> None:
    table = render_arch_read_table([ToolInfo("artifact_query_stats", "Counts things.")])

    assert "| `artifact_query_stats` | Read-only | Counts things. |" in table


def test_generate_documents_reports_stale_content(tmp_path: Path) -> None:
    modeling = tmp_path / "docs/03-modeling"
    assurance = tmp_path / "docs/04-assurance"
    modeling.mkdir(parents=True)
    assurance.mkdir(parents=True)
    marker = "<!-- mcp-tools:begin arch-read -->\nold\n<!-- mcp-tools:end arch-read -->\n"
    (modeling / "interfaces-and-mcp.md").write_text(marker)
    (assurance / "mcp-tools.md").write_text(
        "<!-- mcp-tools:begin assurance-read -->\nold\n<!-- mcp-tools:end assurance-read -->\n"
    )

    documents = generate_documents(tmp_path, {"arch-read": "new", "assurance-read": "new"})

    assert all(isinstance(document, GeneratedDocument) for document in documents)
    assert all(document.changed for document in documents)
    assert "-old" in documents[0].diff()
    assert "+new" in documents[0].diff()


def test_unknown_readme_mentions(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Use `artifact_query_stats` and `artifact_missing`.")

    assert unknown_readme_mentions(tmp_path, {"artifact_query_stats"}) == {"artifact_missing"}
