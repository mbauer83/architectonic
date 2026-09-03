"""The backend watches the repositories it was told to serve, and no others.

`arch-backend --repo-root X` served X while watching Y. The watcher was auto-started with no
arguments, so it resolved the *process default* engagement root — `ARCH_MCP_MODEL_REPO_ROOT`, then
`ARCH_REPO_ROOT`, then the nearest `arch-workspace.yaml` found by walking up from the working
directory — which is only the served root by coincidence.

Measured against a real backend, with a second process doing the writing:

* an entity whose file had been deleted stayed listed,
* an entity created out-of-band never appeared,
* seven connections removed by another process were still reported thirty seconds later, with no
  self-healing.

All three are the same fault, and all three converge within about six seconds once the roots agree.
That matters beyond staleness: the product ships stdio MCP write servers *and* a backend over one
workspace, so "another process wrote to the repository" is the normal case, not an edge one.

The second half is the enterprise root. `repo_scope="both"` resolves a *default* enterprise root when
none is passed, so a backend serving no enterprise repository would watch one it does not serve —
the same fault in the half nobody had looked at.

**Stated as an equality, not as a spelling.** The test asserts that the roots handed to the watcher
resolve to exactly `state.configured_roots()`, which is where the backend records what it serves.
Asserting the argument names instead would pass a version that spelled them correctly and still
resolved somewhere else, and it would have to be rewritten by anyone changing engagements at runtime
rather than telling them what to preserve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import src.infrastructure.backend.arch_backend_app as backend_app
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_roots
from src.infrastructure.rest.routers import state as served_state


@pytest.fixture()
def watcher_calls(monkeypatch) -> list[dict[str, Any]]:
    """What the watcher was asked to watch, without starting one."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(backend_app, "auto_start_default_watcher", lambda **kw: calls.append(kw) or {})
    return calls


@pytest.fixture()
def serving(monkeypatch):
    """Put the backend's served-root state in a known place, and restore it."""

    def _serve(engagement: Path | None, enterprise: Path | None = None) -> None:
        monkeypatch.setattr(served_state, "_repo_root", engagement, raising=False)
        monkeypatch.setattr(served_state, "_enterprise_root", enterprise, raising=False)

    return _serve


ENGAGEMENT = Path("/srv/workspace/engagements/ENG-T/architecture-repository")
ENTERPRISE = Path("/srv/workspace/enterprise-repository")


def test_it_watches_the_engagement_root_the_backend_serves(watcher_calls, serving) -> None:
    serving(ENGAGEMENT)

    backend_app._watch_the_roots_this_backend_serves()

    assert len(watcher_calls) == 1
    assert Path(watcher_calls[0]["repo_root"]) == ENGAGEMENT


def test_it_watches_both_roots_when_an_enterprise_repository_is_served(watcher_calls, serving) -> None:
    serving(ENGAGEMENT, ENTERPRISE)

    backend_app._watch_the_roots_this_backend_serves()

    assert Path(watcher_calls[0]["repo_root"]) == ENGAGEMENT
    assert Path(watcher_calls[0]["enterprise_root"]) == ENTERPRISE


def test_it_does_not_watch_an_enterprise_repository_the_backend_does_not_serve(
    watcher_calls, serving
) -> None:
    """`repo_scope="both"` resolves a default enterprise root. A backend serving none must not
    inherit one, or it watches a repository nobody asked it about."""
    serving(ENGAGEMENT, None)

    backend_app._watch_the_roots_this_backend_serves()

    assert watcher_calls[0]["repo_scope"] == "engagement"
    assert watcher_calls[0]["enterprise_root"] is None


@pytest.mark.parametrize("enterprise", [None, ENTERPRISE], ids=["engagement-only", "both-roots"])
def test_the_watched_roots_are_exactly_the_served_roots(watcher_calls, serving, enterprise) -> None:
    """The guarantee, as an equality: whatever the watcher was asked to watch must resolve to the
    same repositories the backend records as served. A spelling can be right while the resolution
    is wrong, and that is the defect this file exists for."""
    serving(ENGAGEMENT, enterprise)

    backend_app._watch_the_roots_this_backend_serves()

    watched = resolve_repo_roots(
        repo_scope=watcher_calls[0]["repo_scope"],
        repo_root=watcher_calls[0]["repo_root"],
        repo_preset=None,
        enterprise_root=watcher_calls[0]["enterprise_root"],
    )
    assert [p.resolve() for p in watched] == served_state.configured_roots()


def test_an_app_built_without_a_served_repository_is_left_alone(watcher_calls, serving) -> None:
    """`build_app` is used by the test suite without a backend having initialised state. Inventing a
    root for it would be a guess; the default resolution stays, and says so in the log."""
    serving(None, None)

    backend_app._watch_the_roots_this_backend_serves()

    assert watcher_calls == [{}]
