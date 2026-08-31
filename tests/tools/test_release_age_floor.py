"""The release-age floor, over fixtures that state the verdict each source shape earns.

Every case here is constructed by the test, so the assertions are exact — unlike the assertions
against the real lockfiles, which state relations because the locks change whenever a dependency
does. What is pinned here is the *policy*: which shapes pass, which fail, and where the boundary is.

The two that cost the most to get wrong:

* **The youngest artifact decides.** A lock records an upload time per artifact — an sdist and a
  wheel per platform — so a package can carry a year-old sdist beside a wheel published an hour ago.
  Aggregating on the oldest would admit exactly the case the floor exists to catch.
* **Absent evidence is not a pass.** A missing or future timestamp, an unreachable registry, an
  immutable commit sha with no publish date: none of these say the content survived a day.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.supplychain.release_age import (
    FLOOR,
    Admitted,
    ArchiveUrl,
    LocalPath,
    Refused,
    RegistryArtifacts,
    assess,
    vcs_ref,
)

_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
_WORKSPACE = Path("/workspace/project")


def _judge(source: object, workspace: Path = _WORKSPACE) -> Admitted | Refused:
    return assess(source, now=_NOW, workspace=workspace)  # type: ignore[arg-type]


def _uploaded(*ages: timedelta) -> RegistryArtifacts:
    return RegistryArtifacts(uploaded=tuple(_NOW - age for age in ages))


def test_a_pin_older_than_the_floor_is_admitted() -> None:
    assert isinstance(_judge(_uploaded(timedelta(days=3))), Admitted)


def test_exactly_the_floor_is_admitted() -> None:
    """The boundary, decided rather than left to a strict inequality nobody wrote down."""
    assert isinstance(_judge(_uploaded(FLOOR)), Admitted)


def test_a_moment_under_the_floor_is_refused() -> None:
    assert isinstance(_judge(_uploaded(FLOOR - timedelta(seconds=1))), Refused)


def test_the_youngest_artifact_decides_not_the_oldest() -> None:
    """An old sdist beside a wheel published an hour ago is the case the floor exists to catch."""
    verdict = _judge(_uploaded(timedelta(days=400), timedelta(hours=1)))
    assert isinstance(verdict, Refused)
    assert "under the" in verdict.reason


def test_a_missing_upload_time_is_refused() -> None:
    source = RegistryArtifacts(uploaded=(_NOW - timedelta(days=9), None))
    verdict = _judge(source)
    assert isinstance(verdict, Refused)
    assert "no upload time" in verdict.reason


def test_a_future_upload_time_is_refused() -> None:
    verdict = _judge(_uploaded(-timedelta(hours=2)))
    assert isinstance(verdict, Refused)
    assert "in the future" in verdict.reason


def test_a_pin_with_no_artifacts_at_all_is_refused() -> None:
    assert isinstance(_judge(RegistryArtifacts(uploaded=())), Refused)


@pytest.mark.parametrize(
    "version_shape",
    ["2.10.1", "3.0.0rc1", "1.0.0.dev7", "0.38.0"],
    ids=["release", "prerelease", "dev-build", "yanked-elsewhere"],
)
def test_the_version_string_never_changes_the_verdict(version_shape: str) -> None:
    """A prerelease, a dev build and a version yanked upstream are all judged by their age alone.

    The policy takes a source, not a version: there is no path by which a version string could earn
    a package an exemption, and this fixture is what stops one being added quietly.
    """
    del version_shape
    assert isinstance(_judge(_uploaded(timedelta(days=2))), Admitted)


def test_windows_only_wheels_are_still_judged() -> None:
    """A pin this platform never installs is still in the lock, so it is still in the closure."""
    assert isinstance(_judge(_uploaded(timedelta(hours=2))), Refused)


def test_the_project_itself_passes_by_construction() -> None:
    """A rule failing every non-registry source would make the project need an exception to itself."""
    verdict = _judge(LocalPath(path=_WORKSPACE / "."))
    assert isinstance(verdict, Admitted)
    assert "first-party" in verdict.reason


def test_a_local_path_outside_the_workspace_is_refused() -> None:
    assert isinstance(_judge(LocalPath(path=Path("/elsewhere/vendored"))), Refused)


def test_an_immutable_commit_is_refused_for_want_of_age_evidence() -> None:
    """Integrity is not age: a sha proves what the content is, not that it survived a day."""
    reference = "https://example.invalid/pkg.git#" + "a" * 40
    source = vcs_ref(reference)
    assert source.immutable
    verdict = _judge(source)
    assert isinstance(verdict, Refused)
    assert "no age evidence" in verdict.reason


def test_a_mutable_ref_is_refused_for_a_different_reason() -> None:
    source = vcs_ref("https://example.invalid/pkg.git#main")
    assert not source.immutable
    verdict = _judge(source)
    assert isinstance(verdict, Refused)
    assert "can change" in verdict.reason


def test_a_hashed_archive_is_refused_and_an_unhashed_one_says_more() -> None:
    hashed = _judge(ArchiveUrl(url="https://example.invalid/p.tar.gz", hashed=True))
    unhashed = _judge(ArchiveUrl(url="https://example.invalid/p.tar.gz", hashed=False))
    assert isinstance(hashed, Refused) and isinstance(unhashed, Refused)
    assert hashed.reason != unhashed.reason
