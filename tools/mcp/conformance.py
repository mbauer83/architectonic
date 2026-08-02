"""Call every read-mount MCP tool through the transport a client actually uses.

MCP had no oracle at all. Its 82 tools are covered by tests that call the tool *functions* — the same
"assert what I injected" shape as every other unit test — and nothing invoked one through the
JSON-RPC transport. So nothing knew whether a tool is registered, whether its declared input schema
matches what it accepts, or whether its result is decodable by the client that asked. The two worst
defects of 0.2.0 were both a value crossing a boundary nothing tested; this is a boundary with no
test on either side of the crossing.

This is the MCP analogue of `npm run conformance`: a real `ClientSession` over
`streamable_http`, against the four mounts the backend serves, calling each tool once and reading
the answer. The same principle — the client that fails in production is the only oracle worth
having — and the same shape of register for what is not covered yet.

Usage:
    uv run tools/mcp/conformance.py                      # walk the read mounts
    uv run tools/mcp/conformance.py --url http://host:8000
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_URL = "http://localhost:8000"

#: Mounts this walk covers. The two write mounts (`write`, `assurance-write`: 47 tools) are absent for
#: the same reason the GUI harness's write half is: run against the dogfood repository and the live
#: confidential store, they would author and destroy real content. They need the seeded fixture
#: repository of handoff §1.4, and that is the next slice — recorded here rather than left implicit,
#: because "the walk covers MCP" would otherwise read as covering all 82.
READ_MOUNTS = ("read", "assurance-read")
WRITE_MOUNTS = ("write", "assurance-write")


@dataclass(frozen=True, slots=True)
class Seed:
    """Identifiers discovered from the catalogue reads, so nothing is hard-coded.

    Same rule as the GUI harness: a literal id would make this depend on live model content, which
    CLAUDE.md forbids, and would break the first time somebody authored an entity. A seed that cannot
    be discovered fails the steps that need it and names itself — an unexercised tool reported as a
    pass is the green lie this exists to refuse.
    """

    entity_id: str | None = None
    artifact_id: str | None = None
    assurance_node_id: str | None = None
    anchor_entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool, and the arguments to call it with.

    ``arguments`` takes the seed rather than being a literal mapping, because most of these need an
    identifier that only a catalogue read can supply.
    """

    tool: str
    arguments: Callable[[Seed], Mapping[str, Any]] = field(default=lambda _seed: {})
    #: Seed attributes the call cannot be made without.
    needs: tuple[str, ...] = ()


#: What to call each read-mount tool with. Every tool the mounts list is either here or in
#: :data:`UNEXERCISED` with a reason; the walk asserts that, so a newly registered tool cannot arrive
#: uncalled and unnoticed.
READ_CALLS: tuple[ToolCall, ...] = (
    # ── repo read ─────────────────────────────────────────────────────────────
    ToolCall("artifact_query_stats"),
    ToolCall("artifact_query_list_artifacts"),
    ToolCall("artifact_query_read_artifact", lambda s: {"artifact_id": s.artifact_id}, ("artifact_id",)),
    ToolCall("artifact_query_search_artifacts", lambda _s: {"query": "architecture", "limit": 5}),
    ToolCall(
        "artifact_query_find_connections_for",
        lambda s: {"entity_id": s.entity_id},
        ("entity_id",),
    ),
    ToolCall("artifact_query_find_neighbors", lambda s: {"entity_id": s.entity_id}, ("entity_id",)),
    ToolCall(
        "artifact_diagram_scaffold",
        lambda s: {"entity_ids": [s.entity_id], "diagram_name": "Conformance scaffold"},
        ("entity_id",),
    ),
    ToolCall("artifact_query_datatype_types"),
    ToolCall("artifact_query_viewpoint", lambda _s: {"action": "list"}),
    ToolCall("artifact_aibom_export"),
    ToolCall("artifact_aibom_coverage"),
    ToolCall("artifact_verify"),
    # ── assurance read ────────────────────────────────────────────────────────
    ToolCall("assurance_store_status"),
    ToolCall("assurance_stats"),
    ToolCall("assurance_verify"),
    ToolCall("assurance_list_nodes"),
    ToolCall("assurance_read_node", lambda s: {"node_id": s.assurance_node_id}, ("assurance_node_id",)),
    ToolCall("assurance_list_edges"),
    ToolCall("assurance_list_analyses"),
    ToolCall("assurance_risk_register"),
    ToolCall("assurance_coverage"),
    ToolCall("assurance_case_completeness"),
    ToolCall("assurance_draft_gsn"),
    ToolCall("assurance_fmea_matrix"),
    ToolCall("assurance_stpa_complete"),
    ToolCall("assurance_cast_complete"),
    ToolCall("assurance_grc_complete"),
    ToolCall("assurance_guidance", lambda _s: {"topic": "stpa"}),
    ToolCall("assurance_security_stats"),
    ToolCall("assurance_list_vulnerabilities"),
    ToolCall(
        "assurance_list_bom_components",
        lambda s: {"anchor_entity_id": s.anchor_entity_id},
        ("anchor_entity_id",),
    ),
    ToolCall(
        "assurance_security_metrics",
        lambda s: {"anchor_entity_id": s.anchor_entity_id},
        ("anchor_entity_id",),
    ),
)

#: Read-mount tools this walk does not call, each with why. Shrink-only.
UNEXERCISED: Mapping[str, str] = {
    "assurance_vulnerability_impact": (
        "needs a canonical vulnerability id that exists in the store, which only an ingested signal "
        "snapshot supplies — and ingesting one is a write. Comes with the fixture store."
    ),
    "assurance_scan_ai_candidates": (
        "classifies a caller-supplied list of entities rather than reading the model, so calling it "
        "asserts the classifier and not a boundary. Belongs in a unit test, and has one."
    ),
    "assurance_aibom_export": (
        "takes the AI components to export as its argument, so like the scanner above it exercises a "
        "serialiser over injected input rather than a crossing."
    ),
}


def _text_of(result: Any) -> str:
    """The tool's answer as text. MCP wraps content in a list of typed blocks."""
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _decoded(text: str) -> object:
    """The answer as data. **YAML**, which is what this surface serves.

    verifies: REQ@1776705655.Ga1zwy  (YAML instead of JSON for structured output via MCP)

    The first version of this walk asserted JSON and reported every tool as broken. That is the
    harness being wrong about the contract rather than the contract being wrong — `_dump_yaml_text`
    in `name_normalization` is deliberate, and an agent reading a tool result reads YAML. Worth
    recording, because "the answer is not JSON" is exactly the sort of confident false positive that
    makes a new gate get switched off.
    """
    import yaml

    return yaml.safe_load(text)


def _rows_of(decoded: object) -> list[Mapping[str, Any]]:
    """The list a catalogue read answers with, wherever it put it.

    Some tools wrap their payload in ``result``; others answer a mapping directly. Both are read
    rather than assumed, so a seed does not silently come back empty because the envelope moved.
    """
    if isinstance(decoded, Mapping):
        for key in ("result", "artifacts", "items", "nodes"):
            inner = decoded.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, Mapping)]
    if isinstance(decoded, list):
        return [row for row in decoded if isinstance(row, Mapping)]
    return []


async def _discover_seed(session: Any) -> Seed:
    """Identifiers for the detail reads, from the catalogue reads that publish them."""
    listed = await session.call_tool("artifact_query_list_artifacts", {})
    rows = _rows_of(_decoded(_text_of(listed)))
    # An *entity*, specifically: the list includes diagrams and documents, and the neighbour and
    # connection reads are about entities. Taking row zero gave whatever sorted first.
    entities = [row for row in rows if row.get("record_type") == "entity"]
    first = (entities or rows or [{}])[0]
    artifact_id = first.get("artifact_id")
    return Seed(entity_id=artifact_id, artifact_id=artifact_id)


async def _discover_assurance_seed(session: Any, base: Seed) -> Seed:
    nodes = await session.call_tool("assurance_list_nodes", {})
    rows = _rows_of(_decoded(_text_of(nodes)))
    node_id = (rows[0].get("node_id") or rows[0].get("id")) if rows else None
    # The security reads are anchored on an *architecture* entity, not an assurance node.
    return Seed(
        entity_id=base.entity_id,
        artifact_id=base.artifact_id,
        assurance_node_id=node_id,
        anchor_entity_id=base.entity_id,
    )


async def _walk(url: str) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    by_name = {call.tool: call for call in READ_CALLS}
    failures: list[str] = []
    listed_total = 0
    called_total = 0
    seed = Seed()

    for mount in READ_MOUNTS:
        async with streamablehttp_client(f"{url}/mcp/{mount}") as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = [tool.name for tool in (await session.list_tools()).tools]
                listed_total += len(names)

                uncovered = [n for n in names if n not in by_name and n not in UNEXERCISED]
                if uncovered:
                    failures.append(
                        f"{mount}: these tools are neither called nor registered as unexercised — "
                        f"add a call, or register one with a reason: {sorted(uncovered)}"
                    )

                seed = (
                    await _discover_seed(session)
                    if mount == "read"
                    else await _discover_assurance_seed(session, seed)
                )

                declared = {
                    tool.name: set((tool.inputSchema or {}).get("properties") or {})
                    for tool in (await session.list_tools()).tools
                }

                for name in names:
                    call = by_name.get(name)
                    if call is None:
                        continue
                    missing = [need for need in call.needs if getattr(seed, need) is None]
                    if missing:
                        failures.append(f"{mount}/{name}: SEED absent: {', '.join(missing)}")
                        continue
                    arguments = dict(call.arguments(seed))
                    # A recipe naming a parameter the tool does not declare is *this file* being
                    # wrong, and it is reported as such. The surface already refuses the call —
                    # `_reject_unknown_parameters` is deliberate, and rightly loud — so without the
                    # distinction a stale recipe reads as a broken tool. Telling the two apart is the
                    # same discipline as asking whether the product or the test is wrong when an e2e
                    # spec fails.
                    undeclared = sorted(set(arguments) - declared.get(name, set()))
                    if undeclared:
                        failures.append(
                            f"{mount}/{name}: RECIPE names undeclared parameter(s) {undeclared}; "
                            f"the tool declares {sorted(declared.get(name, set()))}"
                        )
                        continue
                    called_total += 1
                    try:
                        result = await session.call_tool(name, arguments)
                    except Exception as exc:  # noqa: BLE001 - any transport error is this tool's failure
                        failures.append(f"{mount}/{name}: TOOL raised {type(exc).__name__}: {exc}")
                        continue
                    if getattr(result, "isError", False):
                        failures.append(f"{mount}/{name}: TOOL error result: {_text_of(result)[:300]}")
                        continue
                    text = _text_of(result)
                    if not text.strip():
                        failures.append(f"{mount}/{name}: TOOL empty answer")
                        continue
                    try:
                        decoded = _decoded(text)
                    except Exception as exc:  # noqa: BLE001 - a YAML error is the answer being undecodable
                        failures.append(f"{mount}/{name}: TOOL answer is not YAML ({exc}): {text[:200]}")
                        continue
                    if decoded is None:
                        failures.append(f"{mount}/{name}: TOOL answer decoded to nothing: {text[:200]}")

    stale = sorted(set(UNEXERCISED) & set(by_name))
    if stale:
        failures.append(f"registered as unexercised, but a call exists: {stale}")

    print(f"mounts {list(READ_MOUNTS)}: {listed_total} tools listed, {called_total} called")
    print(f"not called, registered with a reason: {len(UNEXERCISED)}")
    print(f"write mounts not walked yet: {list(WRITE_MOUNTS)} (needs the fixture repository)")
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("every listed read-mount tool answered decodable YAML")
    return 0


def _unreachable(url: str) -> str | None:
    """Why the backend cannot be walked, or ``None`` if it can.

    Probed before the walk for the same reason the browser suite probes before its first spec: an
    unreachable target otherwise surfaces as a five-frame `ExceptionGroup` from inside the transport,
    which says what failed and nothing about what to do. The gate did exit 1 — it was simply
    illegible, and an illegible gate is one that gets read as flaky and then ignored.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/api/stats", timeout=5) as response:  # noqa: S310 - local URL
            if response.status >= 500:
                return f"{url} answered HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return None if exc.code < 500 else f"{url} answered HTTP {exc.code}"
    except OSError as exc:
        return f"{url} is not answering ({exc})"
    return None


def main(argv: list[str]) -> int:
    import anyio

    parser = argparse.ArgumentParser(prog="conformance.py", description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="backend base URL")
    args = parser.parse_args(argv[1:])
    url = args.url.rstrip("/")

    reason = _unreachable(url)
    if reason is not None:
        print(
            f"Cannot walk the MCP mounts: {reason}.\n\n"
            "Start the backend, or point the walk at one that is up:\n"
            "  uv run arch-backend --daemon\n"
            "  uv run tools/mcp/conformance.py --url http://host:port\n\n"
            "The assurance mount also needs the confidential store held open — "
            "`uv run arch-assurance unlock`, which `arch-assurance status` will confirm.",
            file=sys.stderr,
        )
        return 1
    return int(anyio.run(_walk, url))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
