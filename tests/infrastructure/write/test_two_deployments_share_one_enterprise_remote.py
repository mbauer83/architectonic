"""Two engagements proposing changes to the same promoted artifact, against one enterprise remote.

This is the arrangement the whole feature is for — B67 is *"proposing changes to promoted artifacts
from a non-admin deployment"*, and there is more than one such deployment. It is also the only race
the write queue cannot help with: that queue serialises writes *within* a process, and these are
two processes with two checkouts that share nothing but a bare repository.

Everything here is real: two enterprise clones of one origin, two engagement repositories, the
actual write path, the actual push. A fake remote would assert the fake.

What must hold, and what each test below pins:

* neither deployment's submission can overwrite the other's branch;
* upstream is what decides integration, so one deployment's merge must not close the other's
  change — that reading is the difference between "somebody accepted this" and "we pushed it";
* and the rebase has to resolve the divergence, putting the second deployment's change on top of
  the first one's merged work rather than beside it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.change_rebase_op import rebase_changes
from src.infrastructure.write.artifact_write.change_submission import submit_changes
from src.infrastructure.write.artifact_write.entity_edit import edit_entity
from src.infrastructure.write.artifact_write.integration_cleanup import close_integrated_changes
from tests.support.git_workflow_fixtures import (
    ENT_ENTITY_ID,
    build_workflow_pair,
    git,
    write_entity,
)


class Deployment:
    """One engagement plus its own clone of the shared enterprise repository."""

    def __init__(self, engagement: Path, enterprise: Path) -> None:
        self.engagement = engagement
        self.enterprise = enterprise
        self.index = combined_artifact_index(engagement, enterprise)
        self.index.refresh()
        self.repo = ArtifactRepository(self.index)

    def close(self) -> None:
        self.index.close()

    def _deps(self):  # noqa: ANN202
        registry = ArtifactRegistry(self.repo._store)  # noqa: SLF001 — the write path is handed one
        return registry, build_artifact_verifier(registry, catalogs=process_runtime_catalogs())

    def record(self, summary: str) -> str:
        registry, verifier = self._deps()
        result = edit_entity(
            repo_root=self.engagement, registry=registry, verifier=verifier,
            clear_repo_caches=lambda _p: self.repo.refresh(), artifact_id=ENT_ENTITY_ID,
            repo=self.repo, dry_run=False, summary=summary,
        )
        self.repo.refresh()
        assert result.artifact_id is not None
        return result.artifact_id

    def submit(self, *ids: str):  # noqa: ANN202
        registry, verifier = self._deps()
        return submit_changes(
            ids, repo=self.repo, enterprise_root=self.enterprise, registry=registry,
            verifier=verifier, clear_repo_caches=lambda _p: self.repo.refresh(),
        )

    def rebase(self, change_id: str):  # noqa: ANN202
        self.repo.refresh()
        proposal = next(
            p
            for group in pending_proposals(
                self.repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
            ).values()
            for p in group
            if p.proposal_id == change_id
        )
        registry, verifier = self._deps()
        return rebase_changes(
            (proposal,), enterprise_root=self.enterprise, repo=self.repo, registry=registry,
            verifier=verifier, clear_repo_caches=lambda _p: self.repo.refresh(),
        )

    def state_of(self, change_id: str) -> str:
        self.repo.refresh()
        record = self.repo.get_entity(change_id)
        assert record is not None
        return str(record.extra.get("proposal-state", ""))

    def fetch(self) -> None:
        """What a deployment learns about the others: whatever its last fetch brought."""
        git(self.enterprise, "fetch", "origin")


@pytest.fixture()
def deployments(tmp_path: Path):  # noqa: ANN201
    """Two deployments sharing one bare origin, each holding the same promoted artifact."""
    engagement_a, enterprise_a = build_workflow_pair(tmp_path)
    git(enterprise_a, "push", "origin", "main")
    origin = tmp_path / "enterprise-origin.git"

    enterprise_b = tmp_path / "b" / "enterprise-repository"
    enterprise_b.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", str(origin), str(enterprise_b)], check=True, capture_output=True)
    for setting, value in (("user.email", "b@example.com"), ("user.name", "Deployment B")):
        git(enterprise_b, "config", setting, value)

    engagement_b = tmp_path / "b" / "engagements" / "ENG-B" / "architecture-repository"
    write_entity(engagement_b, "REQ@1000000701.BEng.b-engagement-requirement", "B Engagement")
    subprocess.run(["git", "init", "-q", str(engagement_b)], check=True, capture_output=True)

    a, b = Deployment(engagement_a, enterprise_a), Deployment(engagement_b, enterprise_b)
    try:
        yield a, b
    finally:
        a.close()
        b.close()


def _remote_branches(enterprise: Path) -> list[str]:
    listing = git(enterprise, "ls-remote", "--heads", "origin")
    return [line.split("refs/heads/", 1)[1] for line in listing.splitlines() if "refs/heads/" in line]


def _merge_into_main(enterprise: Path, branch: str) -> None:
    """A reviewer accepts one deployment's branch."""
    working = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
    git(enterprise, "checkout", "main")
    git(enterprise, "merge", "--no-ff", branch, "-m", f"reviewer merged {branch}")
    git(enterprise, "push", "origin", "main")
    git(enterprise, "checkout", working)
    git(enterprise, "fetch", "origin")


def test_each_deployment_publishes_its_own_branch(deployments) -> None:  # noqa: ANN001
    """Neither overwrites the other. B fetches first, which is what a deployment's sync does, and
    is what lets its branch naming avoid a name origin already holds."""
    a, b = deployments
    first = a.submit(a.record("A's wording"))
    b.fetch()

    second = b.submit(b.record("B's wording"))

    assert first.branch != second.branch
    heads = _remote_branches(a.enterprise)
    assert first.branch in heads
    assert second.branch in heads


def test_a_branch_carries_only_its_own_deployment_change(deployments) -> None:  # noqa: ANN001
    a, b = deployments
    first = a.submit(a.record("A's wording"))
    b.fetch()
    second = b.submit(b.record("B's wording"))

    path = f"model/motivation/requirement/{ENT_ENTITY_ID}.md"
    assert "A's wording" in git(a.enterprise, "show", f"{first.branch}:{path}")
    b.fetch()
    assert "B's wording" in git(b.enterprise, "show", f"{second.branch}:{path}")
    assert "A's wording" not in git(b.enterprise, "show", f"{second.branch}:{path}")


def test_one_deployments_merge_does_not_close_the_others_change(deployments) -> None:  # noqa: ANN001
    """The reading that decides it. Both branches carry *a* change to the same artifact, so a sweep
    judging by "the artifact moved" would close B's the moment A's was accepted."""
    a, b = deployments
    a_change, b_change = a.record("A's wording"), b.record("B's wording")
    first = a.submit(a_change)
    b.fetch()
    b.submit(b_change)
    _merge_into_main(a.enterprise, first.branch)
    b.fetch()
    b.repo.refresh()  # what a start does before sweeping

    swept = close_integrated_changes(b.repo)

    assert swept.closed == (), "upstream carries A's wording, not B's"
    assert b.state_of(b_change) == "submitted"


def test_the_merge_does_close_the_change_it_carried(deployments) -> None:  # noqa: ANN001
    """The other half, so the test above is not passing because nothing is ever closed."""
    a, _b = deployments
    a_change = a.record("A's wording")
    first = a.submit(a_change)
    _merge_into_main(a.enterprise, first.branch)
    a.repo.refresh()  # what a start does before sweeping

    swept = close_integrated_changes(a.repo)

    assert [c.proposal_id for c in swept.closed] == [a_change]
    assert a.state_of(a_change) == "integrated"


def test_the_second_deployment_rebases_onto_the_merged_work(deployments) -> None:  # noqa: ANN001
    """The divergence resolved: B's replacement branch sits on the upstream that now carries A's
    merge, rather than beside it — which is what stops the reviewer's merge reverting A."""
    a, b = deployments
    b_change = b.record("B's wording")
    first = a.submit(a.record("A's wording"))
    b.fetch()
    b.submit(b_change)
    _merge_into_main(a.enterprise, first.branch)
    b.fetch()

    report = b.rebase(b_change)

    assert report.republished is not None
    path = f"model/motivation/requirement/{ENT_ENTITY_ID}.md"
    published = git(b.enterprise, "show", f"{report.republished.branch}:{path}")
    assert "B's wording" in published, "B's change is on it"
    assert git(b.enterprise, "merge-base", "--is-ancestor", "origin/main", report.republished.branch) == ""
