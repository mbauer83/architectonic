"""The signal-anchor reader resolves the repository the process was configured to serve.

Every other read surface answers from the roots the server resolved — `--repo-root`, else
`ARCH_REPO_ROOT`, else the arch-init state — and `anchor_reader_for` resolved from `Path.cwd()`
instead, honouring none of the three. A deployment that runs from its workspace was unaffected, which
is why it went unnoticed. Two configurations were not, and they failed differently:

* **roots configured, no workspace config** — the mode `docker/entrypoint.sh` supports explicitly.
  Nothing at or above cwd, so `UnavailableAnchorReader` reported every anchor unknown — deliberately,
  so an ingest fails rather than skipping validation — and every ingest was refused for entities that
  plainly existed.
* **cwd holding a *different* workspace** — the worse case: resolution *succeeded*, against the wrong
  model, and refused an entity belonging to the repository the server was actually serving.

It survived because both existing ingest suites monkeypatch `anchor_reader_for` away
(`test_ingest_security_signals_tool.py`, `test_security_ingest_http.py`): the resolution nothing
exercised is the resolution that broke. Found by pointing the fixture backend at a disposable
repository and asking it to ingest a BOM for an entity it had just authored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.assurance.anchor_reader import (
    IndexAnchorReader,
    UnavailableAnchorReader,
    anchor_reader_for,
)


@pytest.fixture
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with no workspace in it or above it, which is the whole point.

    Under `tmp_path` there is no `arch-workspace.yaml` and no `.arch/init-state.yaml`, so cwd-based
    discovery finds nothing — leaving the environment as the only thing that can answer.
    """
    cwd = tmp_path / "somewhere-else"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


def test_the_environment_configured_root_is_what_it_reads(
    tmp_path: Path, elsewhere: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ARCH_REPO_ROOT` is the deployment seam, so it has to reach this reader.

    Asserted as the reader's *type* because that is the behaviour: `UnavailableAnchorReader` is not a
    degraded reader, it is a refusal of every anchor, and it is what a deployment used to get for
    entities that exist.
    """
    engagement = tmp_path / "engagement"
    engagement.mkdir()
    monkeypatch.setenv("ARCH_REPO_ROOT", str(engagement))
    monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)

    reader = anchor_reader_for()

    assert isinstance(reader, IndexAnchorReader), (
        "the configured repository was ignored, so every ingest anchored on a real entity is refused"
    )


def test_both_roots_are_honoured_together(
    tmp_path: Path, elsewhere: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An anchor promoted to enterprise still has to resolve, which the docstring already promises.

    The combined index is what makes that true, so the enterprise root cannot be the one variable the
    reader drops.
    """
    engagement = tmp_path / "engagement"
    enterprise = tmp_path / "enterprise"
    for root in (engagement, enterprise):
        root.mkdir()
    monkeypatch.setenv("ARCH_REPO_ROOT", str(engagement))
    monkeypatch.setenv("ARCH_ENTERPRISE_ROOT", str(enterprise))

    assert isinstance(anchor_reader_for(), IndexAnchorReader)


def test_with_nothing_configured_it_still_refuses_rather_than_guessing(
    elsewhere: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fail-closed half, kept: no configuration is not permission to allow every anchor.

    `UnavailableAnchorReader` exists so an ingest fails when the model cannot be consulted, because
    degrading to "allow everything" would make the check advisory exactly when it is least verifiable.
    Honouring the environment must not turn into inventing a root when there is none.
    """
    monkeypatch.delenv("ARCH_REPO_ROOT", raising=False)
    monkeypatch.delenv("ARCH_ENTERPRISE_ROOT", raising=False)

    assert isinstance(anchor_reader_for(), UnavailableAnchorReader)


def test_an_explicit_root_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller's argument outranks the environment, matching `resolve_server_roots`' precedence."""
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    monkeypatch.setenv("ARCH_REPO_ROOT", str(tmp_path / "ignored"))

    assert isinstance(anchor_reader_for(explicit), IndexAnchorReader)
