from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from .aibom_read_tools import register_aibom_read_tools
from .install_read_cache import install_read_result_cache
from .query_datatype_tools import register_query_datatype_tools
from .query_graph_tools import register_query_graph_tools
from .query_list_read_tools import register_query_list_read_tools
from .query_scaffold_tools import register_query_scaffold_tools
from .query_search_tools import register_query_search_tools
from .query_stats_tools import register_query_stats_tools
from .query_viewpoint_tools import register_query_viewpoint_tools
from .read_result_cache import ReadResultCache

#: One cache per process, shared by every registered read server.
READ_RESULT_CACHE = ReadResultCache()


def register_query_tools(mcp: FastMCP) -> None:
    """Register all model query tools."""

    register_query_stats_tools(mcp)
    register_query_list_read_tools(mcp)
    register_query_search_tools(mcp)
    register_query_graph_tools(mcp)
    register_query_scaffold_tools(mcp)
    register_query_datatype_tools(mcp)
    register_query_viewpoint_tools(mcp)
    register_aibom_read_tools(mcp)

    # Applied last, over the tools just registered: agent traffic re-asks the same questions
    # in bursts, and MCP calls are JSON-RPC POSTs that the HTTP conditional-GET path cannot
    # help. Bounded and stamped with the read-model generation, so a hit is never stale.
    install_read_result_cache(mcp, READ_RESULT_CACHE)
