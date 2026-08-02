"""The MCP write walk runs, and what it covers stays covered.

The walk is the oracle — `uv run tools/mcp/conformance.py --fixture`. This is what keeps it honest in
the suite, and it asserts the same three properties as the REST walk's test for the same reasons.

**It runs green** — every declared tool is invoked over the real JSON-RPC transport, against a real
backend serving disposable content, and every declared mutation reports that it wrote.

**Its register is shrink-only and reasoned.** `WRITE_UNEXERCISED` holds preconditions the fixture does
not build. A tool must not be both invoked and registered as unexercised, because that is how a
register starts describing a state of affairs that ended.

**The register is complete against the served surface.** Every tool the mount lists is in one bucket or
the other, so a newly registered write tool cannot arrive uninvoked and unnoticed — which is the
condition the whole register exists to detect.

Why over the transport at all: the write mount's 25 tools were covered by tests that call the tool
*functions*. The first transport run of this walk found `artifact_admin_reindex` deadlocking on its own
write-queue job, invisible to every one of them, because a tool invoked through the mount is *submitted*
to the write queue and a tool called directly is not. See
`tests/infrastructure/test_write_drain_does_not_wait_on_itself.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.mcp import conformance, write_walk
from tools.quality.fixture_backend import fixture_backend
from tools.quality.fixture_workspace import FixtureWorkspace


def test_the_register_is_reasoned() -> None:
    for tool, reason in write_walk.WRITE_UNEXERCISED.items():
        # A one-line reason is a reason nobody can act on; these have to survive being read.
        assert len(reason) > 80, (tool, reason)
    assert len(write_walk.ASSURANCE_WRITE_MOUNT_REASON) > 80


def test_no_tool_is_both_invoked_and_registered_as_unexercised() -> None:
    invoked = {call.tool for call in write_walk.WRITE_CALLS}
    overlap = invoked & set(write_walk.WRITE_UNEXERCISED)
    assert overlap == set(), sorted(overlap)


def test_every_call_can_build_its_arguments_in_declared_order() -> None:
    """Declaration order *is* the walk's dependency order, and this is where breaking it is noticed.

    Each recipe addresses ids an earlier call captured. Get the order wrong and the walk reports "needs
    'entity' from a call that did not run" — a real failure, but one that needs a backend and twenty
    seconds to surface. Replaying the recipes against placeholder ids asks the same question in
    milliseconds, using the walk's own mechanism rather than a second description of it.
    """
    context = write_walk.WriteContext(workspace=_placeholder_workspace())
    for call in write_walk.WRITE_CALLS:
        try:
            call.arguments(context)
        except KeyError as missing:
            pytest.fail(f"{call.tool} addresses {missing}, which no earlier call captures")
        for capture in call.captures:
            context.created[capture.key] = f"<{capture.key}>"


def _placeholder_workspace() -> FixtureWorkspace:
    """A workspace shaped like the real one, with ids that are obviously not real.

    Shaped rather than built: `build_fixture_workspace` authors a repository through the write tools,
    which is twenty seconds of work to answer a question about the order of a tuple.
    """
    return FixtureWorkspace(
        root=Path("/nonexistent"),
        engagement_root=Path("/nonexistent/engagement"),
        enterprise_root=Path("/nonexistent/enterprise"),
        authored={
            "connected_entities": ["<source-entity>", "<target-entity>"],
            "unreferenced_entity": ["<unreferenced-entity>"],
            "diagram": ["<diagram>"],
        },
    )


@pytest.mark.slow_walk
def test_the_walk_runs_green_against_a_fixture_backend() -> None:
    """The whole point: every declared write tool is invoked over the transport and answers as declared.

    One backend, because `fixture_backend` serialises on a cross-process lock — two would queue, and the
    second would be addressing content the first had already destroyed.
    """
    import anyio

    with fixture_backend() as backend:
        report = anyio.run(_walk, backend.base_url, backend.workspace)

    assert report.failures == [], report.failures
    assert report.called == len(write_walk.WRITE_CALLS), (report.called, len(write_walk.WRITE_CALLS))
    # Complete against the served surface: nothing the mount lists is missing from both buckets. The
    # walk reports that as a failure, so an empty `failures` above already proves it — this asserts the
    # count so a mount that stopped listing tools altogether cannot pass by serving nothing.
    #
    # *Distinct* tools, not calls: `artifact_save_changes` is invoked twice, once per repository target,
    # because the two take different paths through `enterprise_git_ops` and covering only the default
    # would report the tool covered on half its contract.
    covered = {call.tool for call in write_walk.WRITE_CALLS}
    assert report.listed == len(covered) + len(write_walk.WRITE_UNEXERCISED), (report.listed, len(covered))


async def _walk(url: str, workspace: object) -> conformance.Report:
    report = conformance.Report()
    await conformance.walk_writes(url, workspace, report)
    return report
