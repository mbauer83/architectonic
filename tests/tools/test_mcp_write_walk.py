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

#: Both write mounts, as (name, calls, register), so every property below is asserted of each.
#:
#: Parameterised rather than duplicated: `assurance-write` arrived with 22 tools of its own, and the
#: three questions this file asks — is the register reasoned, is anything in both buckets, can every
#: recipe build its arguments in declared order — are the same questions on either mount. A second copy
#: of them is the copy that would stop being updated.
_MOUNTS = (
    (write_walk.MOUNT, write_walk.WRITE_CALLS, write_walk.WRITE_UNEXERCISED),
    (write_walk.ASSURANCE_MOUNT, write_walk.ASSURANCE_WRITE_CALLS, write_walk.ASSURANCE_WRITE_UNEXERCISED),
)


@pytest.mark.parametrize(("mount", "calls", "register"), _MOUNTS)
def test_the_register_is_reasoned(mount: str, calls: object, register: dict[str, str]) -> None:
    for tool, reason in register.items():
        # A one-line reason is a reason nobody can act on; these have to survive being read.
        assert len(reason) > 80, (mount, tool, reason)


@pytest.mark.parametrize(("mount", "calls", "register"), _MOUNTS)
def test_no_tool_is_both_invoked_and_registered_as_unexercised(
    mount: str, calls: tuple[write_walk.WriteCall, ...], register: dict[str, str]
) -> None:
    overlap = {call.tool for call in calls} & set(register)
    assert overlap == set(), (mount, sorted(overlap))


@pytest.mark.parametrize(("mount", "calls", "register"), _MOUNTS)
def test_every_call_can_build_its_arguments_in_declared_order(
    mount: str, calls: tuple[write_walk.WriteCall, ...], register: dict[str, str]
) -> None:
    """Declaration order *is* the walk's dependency order, and this is where breaking it is noticed.

    Each recipe addresses ids an earlier call captured. Get the order wrong and the walk reports "needs
    'entity' from a call that did not run" — a real failure, but one that needs a backend and twenty
    seconds to surface. Replaying the recipes against placeholder ids asks the same question in
    milliseconds, using the walk's own mechanism rather than a second description of it.
    """
    context = write_walk.WriteContext(
        workspace=_placeholder_workspace(), fmea_basis_digest="<basis-digest>"
    )
    for call in calls:
        try:
            call.arguments(context)
        except KeyError as missing:
            pytest.fail(f"{mount}/{call.tool} addresses {missing}, which no earlier call captures")
        except LookupError as missing:
            pytest.fail(f"{mount}/{call.tool} needs a fixture role nothing authors: {missing}")
        for capture in call.captures:
            context.created[capture.key] = f"<{capture.key}>"


def test_the_two_mounts_do_not_share_a_tool_name() -> None:
    """One name on two mounts would make "which mount covered it" unanswerable from the report.

    The counts in `test_the_walk_runs_green_against_a_fixture_backend` are sums across mounts, so a
    shared name would make a tool invoked on one mount look like coverage of the other.
    """
    repository = {call.tool for call in write_walk.WRITE_CALLS}
    assurance = {call.tool for call in write_walk.ASSURANCE_WRITE_CALLS}
    assert repository & assurance == set(), sorted(repository & assurance)


def test_the_assurance_mount_no_longer_carries_an_excuse() -> None:
    """The register said what it was waiting for; the fixture store is what it was waiting for.

    Asserted by absence, because an excuse left beside a walked mount is how a register starts lying —
    a reader would take `assurance-write` for still dark while 22 tools were being invoked every run.
    """
    assert not hasattr(write_walk, "ASSURANCE_WRITE_MOUNT_REASON")


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
            "application_diagram": ["<diagram>"],
            # The assurance roles the confidential mount's recipes address. Present here so the
            # order check covers that mount too; `_AssuranceRoles` raises `LookupError` naming the
            # module that authors them when one is missing, which the caller turns into a failure.
            "assurance_bare_node": ["<assurance-bare-node>"],
            "assurance_bindable_node": ["<assurance-bindable-node>"],
            "assurance_failure_mode": ["<assurance-failure-mode>"],
            "assurance_edge_conn_type": ["<assurance-conn-type>"],
            "assurance_security_anchor": ["<assurance-anchor-entity>"],
            "assurance_analysis": ["<assurance-analysis>"],
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

    # Both mounts, in one run against one backend — so the counts are sums, and
    # `test_the_two_mounts_do_not_share_a_tool_name` is what keeps a sum from double-counting.
    expected_calls = len(write_walk.WRITE_CALLS) + len(write_walk.ASSURANCE_WRITE_CALLS)
    assert report.called == expected_calls, (report.called, expected_calls)
    assert sorted(report.mounts) == sorted((write_walk.MOUNT, write_walk.ASSURANCE_MOUNT))

    # Complete against the served surface: nothing either mount lists is missing from both buckets. The
    # walk reports that as a failure, so an empty `failures` above already proves it — this asserts the
    # count so a mount that stopped listing tools altogether cannot pass by serving nothing.
    #
    # *Distinct* tools, not calls: `artifact_save_changes` is invoked twice, once per repository target,
    # because the two take different paths through `enterprise_git_ops` and covering only the default
    # would report the tool covered on half its contract.
    covered = {call.tool for call in write_walk.WRITE_CALLS}
    covered |= {call.tool for call in write_walk.ASSURANCE_WRITE_CALLS}
    registered = len(write_walk.WRITE_UNEXERCISED) + len(write_walk.ASSURANCE_WRITE_UNEXERCISED)
    assert report.listed == len(covered) + registered, (report.listed, len(covered))


async def _walk(url: str, workspace: object) -> conformance.Report:
    report = conformance.Report()
    await conformance.walk_writes(url, workspace, report)
    return report
