"""v1 deliberately exposes NO public snapshot-lifecycle transport (F3.16/F3.17):
the IngestSecuritySignals command owns staging → populate → complete → activate,
and transports submit a bundle to it rather than driving the transitions. REST and
MCP must not grow staging/activation/failure routes — a new one is a conscious
decision, not an accident this test would miss.

``security-ingest`` is NOT forbidden: it is the one sanctioned mutation surface,
and it submits a whole bundle rather than stepping the lifecycle."""

from __future__ import annotations

# Path fragments that would indicate a lifecycle-stepping route: the aggregate
# name in either spelling, and the transition verbs themselves.
_FORBIDDEN_FRAGMENTS = (
    "signal-snapshot", "signal_snapshot", "snapshot-lifecycle",
    "activate", "supersede", "staging",
)


def test_rest_exposes_no_snapshot_lifecycle_route() -> None:
    from src.infrastructure.gui.routers.assurance import router
    from tests.support.route_introspection import openapi_paths

    paths = openapi_paths(router)
    offenders = {
        path for path in paths
        if any(fragment in path for fragment in _FORBIDDEN_FRAGMENTS)
    }
    assert offenders == set(), (
        f"snapshot-lifecycle REST routes are deliberately absent in v1: {offenders}"
    )
    # The read-side metrics endpoint IS expected — reads never drive lifecycle.
    assert "/api/assurance/security-metrics" in paths


def test_mcp_write_surface_exposes_no_snapshot_lifecycle_tool() -> None:
    import inspect

    from src.infrastructure.mcp.assurance_mcp import security_write_tools, write_tools

    source = inspect.getsource(write_tools) + inspect.getsource(security_write_tools)
    tool_names = {
        line.split('name="')[1].split('"')[0]
        for line in source.splitlines()
        if 'name="' in line
    }
    offenders = {
        name for name in tool_names
        if any(fragment in name for fragment in
               ("activate", "supersede", "staging", "snapshot_lifecycle"))
    }
    assert offenders == set(), (
        f"snapshot-lifecycle MCP tools are deliberately absent in v1: {offenders}"
    )
