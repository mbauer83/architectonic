"""A release is published only from a commit whose CI passed.

`release.yml` runs on the tag push and publishes the assets `arch-update` installs. Until 0.12.0 it ran
beside `ci.yml` rather than after it, so a tag on a red commit published anyway. Since then it called
`ci.yml` as a job, which ran every gate a second time on the commit `main`'s push had just verified.
It now accepts that run — `ci.yml`, pushed to `main`, for exactly the tagged commit — and calls `ci.yml`
only when there is none that passed. These tests hold that shape.
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


def test_main_ci_counts_only_for_the_same_commit_pushed_to_main() -> None:
    jobs = _workflow("release.yml")["jobs"]
    verdict = jobs["main-ci-verdict"]
    script = "\n".join(step.get("run", "") for step in verdict["steps"])
    for condition in ("workflows/ci.yml/runs", "head_sha=${GITHUB_SHA}", "event=push", "branch=main"):
        assert condition in script, condition
    assert '"completed success"' in script, "only a completed, successful run is accepted"
    assert verdict["permissions"] == {"actions": "read"}


def test_ci_runs_on_the_tag_unless_main_ci_passed_and_publish_needs_one_of_the_two() -> None:
    jobs = _workflow("release.yml")["jobs"]
    assert jobs["ci"]["if"] == "needs.main-ci-verdict.outputs.passed != 'true'"
    condition = jobs["publish"]["if"]
    assert "!cancelled()" in condition
    assert "needs.main-ci-verdict.outputs.passed == 'true'" in condition
    assert "needs.ci.result == 'success'" in condition
