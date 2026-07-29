#!/usr/bin/env python3
"""Generate MCP tool reference tables in the documentation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.infrastructure.docs.mcp_docs import (
    collect_tools,
    generate_documents,
    render_arch_read_table,
    render_arch_write_table,
    render_assurance_read_table,
    render_assurance_write_table,
    unknown_readme_mentions,
    write_documents,
)
from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read, mcp_assurance_write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated MCP docs are stale")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    arch_read = collect_tools(mcp_read)
    arch_write = collect_tools(mcp_write)
    assurance_read = collect_tools(mcp_assurance_read)
    assurance_write = collect_tools(mcp_assurance_write)

    regions = {
        "arch-read": render_arch_read_table(arch_read),
        "arch-write": render_arch_write_table(arch_write),
        "assurance-read": render_assurance_read_table(assurance_read),
        "assurance-write": render_assurance_write_table(assurance_write),
    }
    documents = generate_documents(repo_root, regions)

    known_tools = {
        tool.name
        for group in (arch_read, arch_write, assurance_read, assurance_write)
        for tool in group
    }
    unknown = unknown_readme_mentions(repo_root, known_tools)
    if unknown:
        print(f"WARNING: README mentions unknown MCP tool(s): {', '.join(sorted(unknown))}", file=sys.stderr)

    stale = [document for document in documents if document.changed]
    if args.check:
        if stale:
            for document in stale:
                print(document.diff(), end="")
            return 1
        return 0

    write_documents(documents)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
