"""A release is published only from a commit whose CI passed.

`release.yml` runs on the tag push and publishes the assets `arch-update` installs. Until 0.12.0 it ran
beside `ci.yml` rather than after it, so a tag on a red commit published anyway. The release workflow
now calls `ci.yml` as a job and the publish job needs it; these tests hold that shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.yaml_documents import parse_yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _workflow(name: str) -> dict[str, Any]:
    document = parse_yaml((_WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _triggers(document: dict[str, Any]) -> dict[str, Any]:
    # YAML 1.1 reads a bare `on` key as the boolean True.
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict), triggers
    return triggers


def test_ci_keeps_its_own_triggers_and_can_be_called() -> None:
    triggers = _triggers(_workflow("ci.yml"))
    assert "push" in triggers and "pull_request" in triggers
    assert "workflow_call" in triggers


def test_publishing_needs_ci_on_the_tagged_commit() -> None:
    jobs = _workflow("release.yml")["jobs"]
    calling = [name for name, job in jobs.items() if job.get("uses") == "./.github/workflows/ci.yml"]
    assert calling, "release.yml must call ci.yml"
    needs = jobs["publish"].get("needs")
    needed = {needs} if isinstance(needs, str) else set(needs or ())
    assert needed & set(calling), "the publish job must need the CI job"


def test_the_called_ci_gets_the_codecov_secret_and_no_write_access() -> None:
    document = _workflow("release.yml")
    ci_job = next(job for job in document["jobs"].values() if job.get("uses") == "./.github/workflows/ci.yml")
    assert ci_job.get("secrets") == "inherit"
    assert ci_job.get("permissions") == {"contents": "read"}
    assert document.get("permissions") == {"contents": "read"}
    assert document["jobs"]["publish"]["permissions"]["contents"] == "write"


def test_a_tag_run_does_not_share_a_concurrency_group_with_main() -> None:
    group = _workflow("ci.yml")["concurrency"]["group"]
    # Keyed by the ref: refs/tags/vX and refs/heads/main never cancel each other.
    assert "github.ref" in group
