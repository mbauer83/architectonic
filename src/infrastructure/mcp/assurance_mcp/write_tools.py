"""Assurance write MCP tools — the composition of every write registration.

Tools registered on arch-assurance-write, and where each one lives:
  node_write_tools      — create_node, add_edge, edit_node, delete_node, delete_edge
  baseline_write_tools  — seal_baseline, register_arch_ref, model_this
  analysis_write_tools  — create_analysis, update_analysis, delete_analysis, promotion_preflight
  fmea_write_tools      — set_fmea_factor
  grouping_write_tools  — groups, filing, membership
  provenance_write_tools— assign_provenance
  security_write_tools  — signal ingest, snapshot delete, aibom reconcile

This module registered the first twelve itself until it reached 361 lines, past the 350-line limit
the guidelines set. `provenance_write_tools` had already been split out for that reason; the split
that keeps this module under the limit for good is by the aggregate each tool mutates, so a new
tool has an obvious home rather than landing here by default.

All node/edge/ref mutations delegate to src.application.assurance.mutations use cases,
which enforce the three-step protocol: unlock-check → write → audit → post-write verify.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.assurance_mcp.analysis_write_tools import register_analysis_write_tools
from src.infrastructure.mcp.assurance_mcp.baseline_write_tools import register_baseline_write_tools
from src.infrastructure.mcp.assurance_mcp.fmea_write_tools import register_fmea_write_tools
from src.infrastructure.mcp.assurance_mcp.grouping_write_tools import register_grouping_write_tools
from src.infrastructure.mcp.assurance_mcp.node_write_tools import register_node_write_tools
from src.infrastructure.mcp.assurance_mcp.provenance_write_tools import (
    register_provenance_write_tools,
)
from src.infrastructure.mcp.assurance_mcp.security_write_tools import register_security_write_tools


def register_write_tools(server: FastMCP) -> None:
    register_security_write_tools(server)
    register_fmea_write_tools(server)
    register_grouping_write_tools(server)
    register_provenance_write_tools(server)
    register_node_write_tools(server)
    register_baseline_write_tools(server)
    register_analysis_write_tools(server)
