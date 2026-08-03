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
    uv run tools/mcp/conformance.py --fixture            # ...and the write mount, disposably
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.mcp import write_walk  # noqa: E402
from tools.mcp._answers import decoded as _decoded  # noqa: E402
from tools.mcp._answers import rows_of as _rows_of  # noqa: E402
from tools.mcp._answers import text_of as _text_of  # noqa: E402

DEFAULT_URL = "http://localhost:8000"

#: Mounts this walk covers, and how. The read mounts are walked against whatever backend `--url`
#: names, because a read cannot damage it. Both write mounts are walked only under `--fixture`:
#: `write` against a repository built to be destroyed, `assurance-write` against a confidential store
#: built the same way — see `write_walk` and `fixture_workspace._build_assurance_store`.
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


@dataclass
class Report:
    """What a walk covered, what it did not, and what went wrong.

    Each walk fills its own `mounts` and `notes` rather than the printer deciding from a flag which
    kind of walk it is looking at: a reporter that branches on "was this the write half" has to be
    edited every time a half is added, and the half already knows.
    """

    mounts: list[str] = field(default_factory=list)
    listed: int = 0
    called: int = 0
    failures: list[str] = field(default_factory=list)
    #: What is not covered, and why — printed verbatim, because the reason is the value.
    notes: list[str] = field(default_factory=list)


async def _walk_reads(url: str, report: Report) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    by_name = {call.tool: call for call in READ_CALLS}
    failures = report.failures
    seed = Seed()
    report.mounts.extend(READ_MOUNTS)
    report.notes.append(f"not called, registered with a reason: {len(UNEXERCISED)}")
    report.notes.append(f"write mounts not walked here: {list(WRITE_MOUNTS)} (pass --fixture)")

    for mount in READ_MOUNTS:
        async with streamable_http_client(f"{url}/mcp/{mount}") as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = [tool.name for tool in (await session.list_tools()).tools]
                report.listed += len(names)

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
                    report.called += 1
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
                        payload = _decoded(text)
                    except Exception as exc:  # noqa: BLE001 - a YAML error is the answer being undecodable
                        failures.append(f"{mount}/{name}: TOOL answer is not YAML ({exc}): {text[:200]}")
                        continue
                    if payload is None:
                        failures.append(f"{mount}/{name}: TOOL answer decoded to nothing: {text[:200]}")

    stale = sorted(set(UNEXERCISED) & set(by_name))
    if stale:
        failures.append(f"registered as unexercised, but a call exists: {stale}")


async def walk_writes(url: str, workspace: Any, report: Report) -> None:
    """Invoke both write mounts' tools against the fixture backend serving ``workspace``.

    Kept here rather than in `write_walk` so every mount shares one listing check: the question "is
    every tool the mount lists either invoked or registered with a reason" is the same question, and
    asking it twice in two places is how the two answers drift.

    The mounts are walked in sequence against one backend. `assurance-write` goes second because its
    `assurance_model_this` writes an entity into the repository the first mount has been counting.
    """
    digest = await _fmea_basis_digest(url, workspace)
    for mount, calls, unexercised, context in (
        (
            write_walk.MOUNT,
            write_walk.WRITE_CALLS,
            write_walk.WRITE_UNEXERCISED,
            write_walk.WriteContext(workspace=workspace),
        ),
        (
            write_walk.ASSURANCE_MOUNT,
            write_walk.ASSURANCE_WRITE_CALLS,
            write_walk.ASSURANCE_WRITE_UNEXERCISED,
            write_walk.WriteContext(workspace=workspace, fmea_basis_digest=digest),
        ),
    ):
        await _walk_one_write_mount(url, report, mount, calls, unexercised, context)


async def _walk_one_write_mount(
    url: str,
    report: Report,
    mount: str,
    calls: tuple[Any, ...],
    unexercised: Any,
    context: Any,
) -> None:
    """List one write mount, invoke its declared calls, and account for every tool it advertises."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    by_name = {call.tool: call for call in calls}
    report.mounts.append(mount)
    report.notes.append(f"{mount}: not invoked, registered with a reason: {len(unexercised)}")
    async with streamable_http_client(f"{url}/mcp/{mount}") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            report.listed += len(tools)

            uncovered = [
                tool.name
                for tool in tools
                if tool.name not in by_name and tool.name not in unexercised
            ]
            if uncovered:
                report.failures.append(
                    f"{mount}: these tools are neither invoked nor registered as "
                    f"unexercised — add a call, or register one with a reason: {sorted(uncovered)}"
                )

            declared = {
                tool.name: set((tool.inputSchema or {}).get("properties") or {}) for tool in tools
            }
            invoked, failures = await write_walk.walk(session, context, declared, calls)
            report.called += len(invoked)
            report.failures.extend(f"{mount}/{failure}" for failure in failures)

            stale = sorted(set(unexercised) & set(by_name))
            if stale:
                report.failures.append(
                    f"{mount}: registered as unexercised, but a call exists: {stale}"
                )
            missing = sorted(set(by_name) - set(declared))
            if missing:
                report.failures.append(
                    f"{mount}: a call names a tool the mount does not list: {missing}"
                )


async def _fmea_basis_digest(url: str, workspace: Any) -> str:
    """Ask the read mount what basis the fixture's failure mode currently derives.

    A read before a write, across two mounts, because that is the product's own workflow: a judgement
    is pinned to the picture of the model it was made against, and the only honest source of that
    picture is the matrix. Composing a digest here would file a judgement against a basis that never
    existed, and `record_factor_assessment` would rightly refuse it — the refusal arriving inside a
    200, which is the shape this whole exercise keeps finding.

    Raises when the matrix cannot answer. The first version returned "" so the write step would fail
    naming `basis_digest` instead — but the assurance mount refuses with a bare `{"error": …}`, a shape
    `_answers.refusal` did not recognise at the time, so the refused write reported itself green. Both
    halves are fixed; this one raises because the walk cannot ask its question without an answer here,
    and a failure at the read says so where a failure at the write only implies it.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from tools.mcp._answers import decoded, text_of

    failure_mode = workspace.assurance.failure_mode
    async with streamable_http_client(f"{url}/mcp/assurance-read") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(
                "assurance_fmea_matrix",
                {"analysis_id": workspace.assurance.analysis},
                read_timeout_seconds=timedelta(seconds=write_walk.CALL_TIMEOUT_SECONDS),
            )
    # YAML, not JSON: `decoded` says why, and it takes the text rather than the result object.
    payload = decoded(text_of(result))
    factor = write_walk.ASSURANCE_FMEA_FACTOR
    digest = _digest_for(payload, failure_mode, factor)
    if not digest:
        raise RuntimeError(
            f"the FMEA matrix reported no {factor!r} basis digest for {failure_mode}, so "
            f"`assurance_set_fmea_factor` has nothing to pin its judgement to. Matrix answer: "
            f"{str(payload)[:600]}"
        )
    return digest


def _digest_for(payload: object, node_id: str, factor: str) -> str:
    """One factor's basis digest for one failure mode, from a matrix answer.

    Searched for rather than indexed: the matrix is a grid whose shape is the analysis's, so the cell
    holding this node is wherever the model puts it, and a positional read would be an assertion about
    content this walk does not own.

    The digest lives at `factors[<factor>].basis_digest`, per `fmea_cells.cell_payload` — *not* in a
    top-level `basis_digests` map, which is how the `Cell` dataclass carries it internally. Reading the
    internal shape found nothing, and the resulting empty digest was refused by the write.
    """
    for cell in _cells(payload):
        if str(cell.get("node_id") or "") != node_id:
            continue
        factors = cell.get("factors")
        entry = factors.get(factor) if isinstance(factors, Mapping) else None
        value = entry.get("basis_digest") if isinstance(entry, Mapping) else None
        if isinstance(value, str) and value:
            return value
    return ""


def _cells(payload: object) -> Iterator[Mapping[str, Any]]:
    """Every mapping in a matrix answer that looks like a cell, however the grid is nested."""
    if isinstance(payload, Mapping):
        if "node_id" in payload and "factors" in payload:
            yield payload
        for value in payload.values():
            yield from _cells(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _cells(item)


def _print_report(report: Report) -> int:
    print(f"mounts {report.mounts}: {report.listed} tools listed, {report.called} called")
    for note in report.notes:
        print(note)
    for failure in report.failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if report.failures:
        print(f"\n{len(report.failures)} failure(s)", file=sys.stderr)
        return 1
    print("every listed tool answered decodably, and every declared mutation wrote")
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


async def _run(url: str, workspace: Any) -> int:
    """Walk the read mounts, or — when a fixture workspace was built — the write mount.

    One or the other, not both. The read mounts are walked against the dogfood repository on purpose:
    what they establish is that the tools survive *real* content, and a fixture holding four entities
    would weaken that rather than add to it. The fixture backend also resolves the confidential store
    from the source tree rather than from the workspace it serves, so `assurance-read` against it would
    be reading the developer's store through a process that has no business being pointed at it.
    """
    report = Report()
    if workspace is None:
        await _walk_reads(url, report)
    else:
        await walk_writes(url, workspace, report)
    return _print_report(report)


def main(argv: list[str]) -> int:
    import anyio

    parser = argparse.ArgumentParser(prog="conformance.py", description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="backend base URL")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help=(
            "build a disposable fixture repository, serve it on its own port, and walk the `write` "
            "mount against that instead of --url. The only way to walk writes: there is deliberately "
            "no flag that points them at a backend somebody else's content is in."
        ),
    )
    args = parser.parse_args(argv[1:])

    if args.fixture:
        from tools.quality.fixture_backend import fixture_backend

        with fixture_backend() as backend:
            print(f"fixture backend on {backend.base_url}, serving {backend.workspace.engagement_root}")
            return int(anyio.run(_run, backend.base_url, backend.workspace))

    url = args.url.rstrip("/")
    reason = _unreachable(url)
    if reason is not None:
        print(
            f"Cannot walk the MCP mounts: {reason}.\n\n"
            "Start the backend, or point the walk at one that is up:\n"
            "  uv run arch-backend --daemon\n"
            "  uv run tools/mcp/conformance.py --url http://host:port\n\n"
            "The assurance mount also needs the confidential store held open — "
            "`uv run arch-assurance unlock`, which `arch-assurance status` will confirm.\n\n"
            "To walk the write mount instead, pass --fixture: it builds and serves its own "
            "repository, so it needs no backend of yours.",
            file=sys.stderr,
        )
        return 1
    return int(anyio.run(_run, url, None))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
