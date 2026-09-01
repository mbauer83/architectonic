import logging
from typing import Any

import yaml  # type: ignore[import-untyped]
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.mcpserver import Context, MCPServer  # type: ignore[import-not-found]
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolRequestParams, CallToolResult, TextContent

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

    MCPServer's argument model ignores extra fields (pydantic ``extra='ignore'``) and this
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
    raise ToolError(
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


def install_call_tool_normalizer(mcp: MCPServer) -> None:
    """Replace the server's `tools/call` handler with one that normalizes, refuses and answers in YAML.

    Three things the default handler does not do, each of which has its own reason:

    * **Normalize the incoming tool name.** A bridge that namespaces its tools sends
      `server:artifact_verify`; the tool is registered as `artifact_verify`.
    * **Refuse an unknown parameter.** The argument model ignores extra fields, so without this a
      mistyped filter is silently dropped and the tool runs with its defaults — a confidently wrong
      answer rather than an error.
    * **Answer in compact YAML.** The content block is what a model reads, and YAML of the same data
      is materially fewer tokens than JSON. Structured content is left exactly as the tool produced
      it, because that is what the output schema describes.

    Registered through `Server.add_request_handler`, which is the sanctioned replacement in `mcp` 2.x
    for the `@server.call_tool()` decorator this used to reach for. The handler mirrors the SDK's own
    `_handle_call_tool`: it builds the same `Context` and returns a `CallToolResult`.
    """

    async def _call_tool_handler(
        ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        try:
            return await _answer(ctx, params)
        except MCPError:
            raise
        except ToolError as refused:
            if isinstance(refused, UnexpectedToolError):
                logger.exception("Tool %r raised an unexpected exception", params.name)
            else:
                # %r keeps caller-supplied text on one line.
                logger.info("Tool %r refused the call: %r", params.name, str(refused))
            return CallToolResult(content=[TextContent(type="text", text=str(refused))], is_error=True)
        except Exception as unexpected:
            logger.exception("Tool %r raised an unexpected exception", params.name)
            return CallToolResult(content=[TextContent(type="text", text=str(unexpected))], is_error=True)

    async def _answer(
        ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult:
        known = {tool.name for tool in mcp._tool_manager.list_tools()}  # type: ignore[attr-defined]
        normalized = normalize_incoming_tool_name(params.name, known_tools=known)
        if normalized != params.name:
            logger.info("Normalized incoming tool name %r -> %r", params.name, normalized)

        arguments = params.arguments or {}
        tool = mcp._tool_manager.get_tool(normalized)  # type: ignore[attr-defined]
        if tool is not None:
            _reject_unknown_parameters(tool, arguments)

        context: Context[Any, Any] = Context(
            request_context=ctx,
            mcp_server=mcp,
            input_params=params,
            subscriptions=mcp._subscriptions,  # type: ignore[attr-defined]
        )
        if tool is not None and tool.fn_metadata.output_schema is not None:
            # A structured tool: let the SDK build the result, then re-render its readable half from
            # the structured half. The two must describe the same data, and the structured half is
            # what the output schema promises, so it is the one to render *from*.
            answered = await mcp._tool_manager.call_tool(  # type: ignore[attr-defined]
                normalized, arguments, context, convert_result=True
            )
            return _rendered_as_yaml(answered, answered.structured_content)

        # An unstructured tool: take what the function returned, before the SDK turns a mapping into
        # a JSON blob. Rendering that blob would mean reading back a syntax just written, and what
        # came out of doing so was the JSON quoted inside a YAML string.
        returned = await mcp._tool_manager.call_tool(  # type: ignore[attr-defined]
            normalized, arguments, context, convert_result=False
        )
        if isinstance(returned, (dict, list)):
            return CallToolResult(content=[TextContent(type="text", text=_dump_yaml_text(returned))])
        if tool is None:
            return CallToolResult(content=[TextContent(type="text", text=str(returned))])
        converted = tool.fn_metadata.convert_result(returned)
        if isinstance(converted, CallToolResult):
            return converted
        raise TypeError(f"tool {normalized!r} converted its result to {type(converted).__name__}")

    mcp._lowlevel_server.add_request_handler(  # type: ignore[attr-defined]
        "tools/call", CallToolRequestParams, _call_tool_handler
    )


def _rendered_as_yaml(result: CallToolResult, data: object | None) -> CallToolResult:
    """Replace a result's readable content with YAML of `data`, keeping everything else as it is.

    An error result is passed through untouched: its content is a sentence written for a reader, and
    YAML of a sentence is the same sentence with quotes around it.
    """
    if result.is_error or data is None:
        return result
    return result.model_copy(update={"content": [TextContent(type="text", text=_dump_yaml_text(data))]})
