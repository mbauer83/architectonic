import logging
from typing import Any

import yaml  # type: ignore[import-untyped]
from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
from mcp.types import TextContent

logger = logging.getLogger(__name__)


def _dump_yaml_text(data: object) -> str:
    dumped = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    if not isinstance(dumped, str):
        raise TypeError("yaml.dump returned non-string output")
    return dumped.rstrip()


def _reject_unknown_parameters(tool: Any, arguments: dict[str, Any]) -> None:
    """Fail loud on an unknown tool parameter instead of silently dropping it.

    FastMCP's argument model ignores extra fields (pydantic ``extra='ignore'``) and this
    handler dispatches with ``validate_input=False``, so without this check a mistyped or
    unrecognized parameter is silently discarded and the tool runs with its defaults — an easy
    way to get a confidently wrong result (e.g. a filter typo returning the full, unfiltered
    payload). The check is skipped for tools whose input schema explicitly opts into
    ``additionalProperties`` (e.g. a ``**kwargs`` signature). The raised message enumerates the
    accepted parameters with their descriptions so the caller can correct the call immediately;
    the low-level server converts it into an ``isError`` tool result.
    """
    schema = getattr(tool, "parameters", None)
    if not isinstance(schema, dict) or schema.get("additionalProperties", False):
        return
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    accepted = set(properties)
    context_kwarg = getattr(tool, "context_kwarg", None)
    if isinstance(context_kwarg, str):
        accepted.add(context_kwarg)
    unknown = [key for key in arguments if key not in accepted]
    if not unknown:
        return
    listed = []
    for pname in sorted(properties):
        spec: dict[str, Any] = properties[pname] if isinstance(properties[pname], dict) else {}
        detail = spec.get("description") or spec.get("title") or ""
        ptype = spec.get("type", "")
        head = f"  - {pname}" + (f" ({ptype})" if ptype else "")
        listed.append(head + (f": {detail}" if detail else ""))
    accepted_block = "\n".join(listed) if listed else "  (this tool takes no parameters)"
    raise ValueError(
        f"Unknown parameter(s) {sorted(unknown)} for tool {tool.name!r}. "
        f"Accepted parameters:\n{accepted_block}"
    )


def normalize_incoming_tool_name(tool_name: str, *, known_tools: set[str]) -> str:
    """Normalize an incoming tool name from bridges that namespace tools."""

    if tool_name in known_tools:
        return tool_name

    for sep in ("-", ":", ".", "/"):
        if sep in tool_name:
            candidate = tool_name.rsplit(sep, 1)[-1]
            if candidate in known_tools:
                return candidate
    return tool_name


def install_call_tool_normalizer(mcp: FastMCP) -> None:
    """Override FastMCP CallTool handler to normalize tool names and emit YAML responses."""

    async def _call_tool_handler(name: str, arguments: dict[str, Any]) -> Any:
        tools = mcp._tool_manager.list_tools()  # type: ignore[attr-defined]
        known = {t.name for t in tools}
        normalized = normalize_incoming_tool_name(name, known_tools=known)
        if normalized != name:
            logger.info("Normalized incoming tool name %r -> %r", name, normalized)
        context = mcp.get_context()
        tool = mcp._tool_manager.get_tool(normalized)  # type: ignore[attr-defined]

        if tool is not None:
            _reject_unknown_parameters(tool, arguments)

        if tool is not None and tool.output_schema is not None:
            # Structured-output tool: use convert_result=True to get the
            # (content_list, structured_dict) tuple, then replace the JSON
            # text content with compact YAML for token efficiency while
            # preserving the structured dict required by outputSchema.
            result = await mcp._tool_manager.call_tool(  # type: ignore[attr-defined]
                normalized, arguments, context=context, convert_result=True
            )
            if isinstance(result, tuple) and len(result) == 2:
                _, structured = result
                yaml_text = _dump_yaml_text(structured)
                return ([TextContent(type="text", text=yaml_text)], structured)
            # MCP contract violation: outputSchema tools must return (list, dict).
            # Returning a bare list here will cause "outputSchema defined but no
            # structured output returned" deep in the MCP stack.
            logger.error(
                "Structured-output tool %r returned %r instead of (list, dict) tuple; "
                "MCP will reject this response. Check that convert_result=True is used "
                "and that the tool function returns a dict.",
                normalized,
                type(result).__name__,
            )
            return result

        # Non-structured tool: get raw Python result and convert to compact YAML.
        result = await mcp._tool_manager.call_tool(  # type: ignore[attr-defined]
            normalized,
            arguments,
            context=context,
            convert_result=False,
        )
        if isinstance(result, (dict, list)):
            yaml_text = _dump_yaml_text(result)
            return [TextContent(type="text", text=yaml_text)]
        # Fall back to FastMCP normal conversion for strings, ContentBlocks, etc.
        if tool is None:
            return [TextContent(type="text", text=str(result))]
        return tool.fn_metadata.convert_result(result)

    mcp._mcp_server.call_tool(validate_input=False)(_call_tool_handler)  # type: ignore[attr-defined]
