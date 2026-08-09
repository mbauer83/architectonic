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
    table = render_arch_read_table(
        [ToolInfo("artifact_query_stats", "Counts things.", read_only=True, destructive=False)]
    )

    assert "| `artifact_query_stats` | Read-only | Counts things. |" in table


class TestTheAccessColumnComesFromTheAnnotations:
    """The published Access column is the tool's own safety hints, not a guess from its name.

    It used to be a substring list — `delete`, `withdraw`, `bulk_delete`, `admin_reindex` — applied
    to a per-table default. That published two annotated-destructive tools as plain "Write"
    (`artifact_edit_connection`, `artifact_promote_to_enterprise`), three read-only tools on the
    write mount as "Write", and one additive tool as "Destructive" because of a word in its name.
    The documentation contradicted the surface it documents.
    """

    def test_a_destructive_tool_reads_destructive_however_it_is_named(self) -> None:
        # The point of the fix: nothing about "edit_connection" suggests destructive, and the
        # substring list is why it was published as an ordinary write for so long.
        tool = ToolInfo("artifact_edit_connection", "Edits.", read_only=False, destructive=True)

        assert tool.access == "Destructive"

    def test_a_name_containing_a_scary_word_is_not_enough(self) -> None:
        """`artifact_admin_reindex` rebuilds a derived index from the files that are the truth."""
        tool = ToolInfo("artifact_admin_reindex", "Rebuilds.", read_only=False, destructive=False)

        assert tool.access == "Write"

    def test_a_read_only_tool_on_a_write_mount_reads_read_only(self) -> None:
        tool = ToolInfo("artifact_help", "Explains.", read_only=True, destructive=False)

        assert tool.access == "Read-only"

    def test_read_only_wins_over_destructive(self) -> None:
        """MCP declares destructiveHint meaningful only when readOnlyHint is false."""
        tool = ToolInfo("assurance_model_this", "Proposes.", read_only=True, destructive=True)

        assert tool.access == "Read-only"

    def test_an_unannotated_tool_is_not_reported_as_read_only(self) -> None:
        """The conservative default, so a missing annotation cannot under-warn in the docs.

        The annotation gates make this unreachable from the real servers; it is here because the
        collector reads `tool.annotations` defensively and a bug there should surface as an
        over-warning rather than a tool documented as safer than it is.
        """
        tool = ToolInfo("artifact_mystery", "Does something.", read_only=False, destructive=False)

        assert tool.access == "Write"


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
