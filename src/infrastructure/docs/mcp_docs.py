"""Generate MCP tool reference tables from registered FastMCP servers."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast


@dataclass(frozen=True)
class ToolInfo:
    """A tool as the documentation describes it: what it is called, what it does, and what it costs.

    ``read_only`` and ``destructive`` come from the tool's own ``ToolAnnotations`` — the same hints
    a host warns a user with. The published Access column used to be guessed from substrings of the
    name instead, which meant the documentation and the served surface could disagree, and did:
    ``artifact_edit_connection`` and ``artifact_promote_to_enterprise`` are both annotated
    destructive and were both published as plain "Write".
    """

    name: str
    description: str
    read_only: bool
    destructive: bool

    @property
    def access(self) -> str:
        """The Access column, derived rather than guessed."""
        if self.read_only:
            return "Read-only"
        return "Destructive" if self.destructive else "Write"


@dataclass(frozen=True)
class GeneratedDocument:
    path: Path
    original: str
    updated: str

    @property
    def changed(self) -> bool:
        return self.original != self.updated

    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                self.original.splitlines(keepends=True),
                self.updated.splitlines(keepends=True),
                fromfile=str(self.path),
                tofile=str(self.path),
            )
        )


class SafetyHints(Protocol):
    """The subset of ``ToolAnnotations`` the published Access column is derived from."""

    readOnlyHint: bool | None  # noqa: N815 - the wire name, fixed by the MCP specification
    destructiveHint: bool | None  # noqa: N815 - as above


class RegisteredTool(Protocol):
    name: str
    description: str | None
    annotations: SafetyHints | None


class ToolManager(Protocol):
    def list_tools(self) -> list[RegisteredTool]: ...


class McpServer(Protocol):
    _tool_manager: ToolManager


RegionMap = dict[str, str]

_MARKER_RE = re.compile(
    r"(?P<begin><!-- mcp-tools:begin (?P<name>[a-z0-9_-]+) -->)"
    r".*?"
    r"(?P<end><!-- mcp-tools:end (?P=name) -->)",
    re.DOTALL,
)
_README_TOOL_RE = re.compile(r"`((?:artifact|assurance)_[a-z0-9_]+)`")

_ARCH_WRITE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Entities", ("artifact_create_entity", "artifact_edit_entity", "artifact_delete_entity")),
    (
        "Connections",
        ("artifact_add_connection", "artifact_edit_connection", "artifact_edit_connection_associations"),
    ),
    (
        "Diagrams",
        ("artifact_create_diagram", "artifact_edit_diagram", "artifact_delete_diagram", "artifact_create_matrix"),
    ),
    ("Documents", ("artifact_create_document", "artifact_edit_document", "artifact_delete_document")),
    ("Bulk", ("artifact_bulk_write", "artifact_bulk_delete")),
    ("Grouping", ("artifact_group",)),
    (
        "Promotion & sync",
        (
            "artifact_promote_to_enterprise",
            "artifact_save_changes",
            "artifact_submit_for_review",
            "artifact_withdraw_changes",
        ),
    ),
    (
        "Guidance & ops",
        ("artifact_authoring_guidance", "artifact_help", "artifact_get_operation", "artifact_admin_reindex"),
    ),
)

_ASSURANCE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Method authoring",
        (
            "assurance_guidance",
            "assurance_create_analysis",
            "assurance_update_analysis",
            "assurance_delete_analysis",
            "assurance_create_node",
            "assurance_edit_node",
            "assurance_delete_node",
            "assurance_add_edge",
            "assurance_delete_edge",
            "assurance_seal_baseline",
        ),
    ),
    (
        "Completeness & coverage",
        (
            "assurance_verify",
            "assurance_coverage",
            "assurance_stpa_complete",
            "assurance_cast_complete",
            "assurance_grc_complete",
            "assurance_case_completeness",
            "assurance_draft_gsn",
            "assurance_promotion_preflight",
        ),
    ),
    (
        "Failure modes",
        (
            "assurance_fmea_matrix",
            "assurance_set_fmea_factor",
        ),
    ),
    (
        "Supply chain / AIBOM",
        (
            "assurance_aibom_export",
            "assurance_scan_ai_candidates",
            "assurance_reconcile_aibom",
        ),
    ),
    (
        "Security signals",
        (
            "assurance_ingest_security_signals",
            "assurance_list_bom_components",
            "assurance_list_vulnerabilities",
            "assurance_security_stats",
            "assurance_security_metrics",
            "assurance_risk_register",
            "assurance_register_arch_ref",
            "assurance_model_this",
        ),
    ),
    (
        "Store administration",
        (
            "assurance_store_status",
            "assurance_stats",
            "assurance_list_analyses",
            "assurance_list_nodes",
            "assurance_read_node",
            "assurance_list_edges",
        ),
    ),
)


def collect_tools(server: object) -> list[ToolInfo]:
    typed_server = cast(McpServer, server)
    return [
        ToolInfo(
            name=tool.name,
            description=first_sentence(tool.description or ""),
            read_only=bool(tool.annotations and tool.annotations.readOnlyHint),
            destructive=bool(tool.annotations and tool.annotations.destructiveHint),
        )
        for tool in sorted(typed_server._tool_manager.list_tools(), key=lambda item: item.name)
    ]


def first_sentence(text: str) -> str:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return ""
    for index, char in enumerate(normalized):
        if char in ".?!" and index + 1 < len(normalized) and normalized[index + 1] == " ":
            if normalized[max(0, index - 3) : index + 1].lower() in {"e.g.", "i.e."}:
                continue
            return normalized[: index + 1]
    return normalized


def replace_regions(text: str, regions: RegionMap) -> str:
    seen: set[str] = set()

    def replacement(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in regions:
            return match.group(0)
        seen.add(name)
        return f"{match.group('begin')}\n{regions[name].rstrip()}\n{match.group('end')}"

    updated = _MARKER_RE.sub(replacement, text)
    missing = sorted(set(regions) - seen)
    if missing:
        raise ValueError(f"Missing MCP docs marker(s): {', '.join(missing)}")
    return updated


def generate_documents(repo_root: Path, regions: RegionMap) -> list[GeneratedDocument]:
    targets = (
        repo_root / "docs/03-modeling/interfaces-and-mcp.md",
        repo_root / "docs/04-assurance/mcp-tools.md",
    )
    generated: list[GeneratedDocument] = []
    seen_regions: set[str] = set()
    for path in targets:
        original = path.read_text()
        document_regions = {name: regions[name] for name in marker_names(original) & set(regions)}
        seen_regions.update(document_regions)
        generated.append(
            GeneratedDocument(path=path, original=original, updated=replace_regions(original, document_regions))
        )
    missing = sorted(set(regions) - seen_regions)
    if missing:
        raise ValueError(f"Missing MCP docs marker(s): {', '.join(missing)}")
    return generated


def marker_names(text: str) -> set[str]:
    return {match.group("name") for match in _MARKER_RE.finditer(text)}


def write_documents(documents: list[GeneratedDocument]) -> None:
    for document in documents:
        if document.changed:
            document.path.write_text(document.updated)


def render_arch_read_table(tools: list[ToolInfo]) -> str:
    rows = ["| Tool | Access | Purpose |", "|---|---|---|"]
    rows.extend(f"| `{tool.name}` | {tool.access} | {escape_table(tool.description)} |" for tool in tools)
    return "\n".join(rows)


def render_arch_write_table(tools: list[ToolInfo]) -> str:
    return render_grouped_table(tools, _ARCH_WRITE_GROUPS)


def render_assurance_read_table(tools: list[ToolInfo]) -> str:
    return render_grouped_table(tools, _ASSURANCE_GROUPS)


def render_assurance_write_table(tools: list[ToolInfo]) -> str:
    return render_grouped_table(tools, _ASSURANCE_GROUPS)


def render_grouped_table(
    tools: list[ToolInfo],
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    """The grouped table, with each row's access taken from the tool rather than from its mount.

    There is no ``default_access`` any more. A mount-wide default was what made the substring
    heuristic necessary — the write mounts serve reads (``artifact_help``, ``assurance_model_this``)
    and destructive writes alongside additive ones, so one default per table was wrong for several
    rows and a list of name fragments was the patch. The annotations say it per tool.
    """
    by_name = {tool.name: tool for tool in tools}
    rows = ["| Capability | Tool | Access | Purpose |", "|---|---|---|---|"]
    covered: set[str] = set()
    for group_name, names in groups:
        for name in names:
            if name in by_name:
                covered.add(name)
                rows.append(render_grouped_row(group_name, by_name[name]))
    for tool in tools:
        if tool.name not in covered:
            rows.append(render_grouped_row("Other", tool))
    return "\n".join(rows)


def render_grouped_row(group_name: str, tool: ToolInfo) -> str:
    return f"| {group_name} | `{tool.name}` | {tool.access} | {escape_table(tool.description)} |"


def escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def readme_tool_mentions(repo_root: Path) -> set[str]:
    return set(_README_TOOL_RE.findall((repo_root / "README.md").read_text()))


def unknown_readme_mentions(repo_root: Path, known_tools: set[str]) -> set[str]:
    return readme_tool_mentions(repo_root) - known_tools
