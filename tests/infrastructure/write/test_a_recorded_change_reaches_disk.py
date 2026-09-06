"""A recorded change on disk, against a real repository and the product's own verifier.

`change_recording.decide` is pure and says what a further edit does. This is the half that needs a
repository: the file it writes must be one the verifier accepts, findable by the readers that look
for it, and — when it supersedes — written before what it replaces is retired.

The verification is the point rather than a formality. A change file carries four frontmatter fields
the verifier has its own rules for (E145 to E149), and a writer that rendered them differently from
what those rules expect would produce a repository the product refuses to read, on the first use of
the feature.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.change_recording import RecordNew, ReviseDraft, SupersedeSubmitted
from src.application.modeling.proposal_edit import ProposalEdit
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSAL_STATE, PROPOSED_CHANGE_TYPE
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.change_materialization import materialize

TARGET = "APP@1780000000.aaaaaaa.payments-service"
EXISTING = "PCH@1780000002.ccccccc.an-earlier-change"


def _target_md() -> str:
    return (
        "---\n"
        f"artifact-id: {TARGET}\n"
        "artifact-type: application-component\n"
        "name: Payments Service\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n<!-- §content -->\n\n"
        "## Payments Service\n\nA service.\n\n"
        "## Properties\n\n| Attribute | Value |\n|---|---|\n| (none) | (none) |\n\n"
    )


def _existing_change_md(state: str) -> str:
    """Shaped like what the product writes, `§display` marker included.

    Without it the file is invalid (E031) — which the fixture only reveals when something re-verifies
    it, as revising does. A fixture that could not survive the product's own verifier is not a
    fixture of the product.
    """
    return (
        "---\n"
        f"artifact-id: {EXISTING}\n"
        "artifact-type: proposed-change\n"
        "name: An earlier change\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        f"proposes-change-to: {TARGET}\n"
        f"proposal-state: {state}\n"
        "base-revision: abc1234\n"
        "recorded-edit:\n"
        "  kind: entity\n"
        f"  artifact-id: {TARGET}\n"
        "  fields:\n"
        "    name: Earlier Name\n"
        "    notes: Written first.\n"
        "---\n\n<!-- §content -->\n\n## An earlier change\n\nBecause.\n\n<!-- §display -->\n"
    )


@pytest.fixture()
def repo_at(tmp_path: Path):  # noqa: ANN201 — a builder, shaped by what each test needs
    def build(existing_state: str | None = None):
        process_runtime_catalogs()
        root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        (root / "model" / "application" / "application-component").mkdir(parents=True, exist_ok=True)
        (root / "model" / "common" / "proposed-change").mkdir(parents=True, exist_ok=True)
        (root / "model" / "application" / "application-component" / f"{TARGET}.md").write_text(
            _target_md(), encoding="utf-8"
        )
        if existing_state is not None:
            (root / "model" / "common" / "proposed-change" / f"{EXISTING}.md").write_text(
                _existing_change_md(existing_state), encoding="utf-8"
            )
        index = shared_artifact_index(root)
        index.refresh()
        return root, ArtifactRepository(index)

    return build


def _edit(**fields: object) -> ProposalEdit:
    return ProposalEdit(kind="entity", artifact_id=TARGET, fields=fields)


def _materialize(outcome, root: Path, repo: ArtifactRepository, *, dry_run: bool = False):  # noqa: ANN001, ANN202
    return materialize(
        outcome,
        repo=repo,
        engagement_root=root,
        verifier=build_artifact_verifier(catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _path: repo.refresh(),
        target_name="Payments Service",
        base_revision="deadbeef",
        dry_run=dry_run,
    )


def _changes(repo: ArtifactRepository) -> dict[str, dict]:
    repo.refresh()
    return {
        record.artifact_id: parse_frontmatter(record.path.read_text(encoding="utf-8")) or {}
        for record in repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
    }


# ── recording the first change ───────────────────────────────────────────────


def test_a_recorded_change_passes_the_products_own_verifier(repo_at) -> None:  # noqa: ANN001
    """The whole reason this is written against a repository."""
    root, repo = repo_at()
    result = _materialize(RecordNew(edit=_edit(name="Payments Platform")), root, repo)

    assert result.wrote, result.verification
    assert result.path.exists()


def test_it_is_findable_by_the_reader_that_looks_for_changes(repo_at) -> None:  # noqa: ANN001
    """`proposed-change` is internal; a repository that excluded internal types from listing would
    write changes nothing could ever read back."""
    root, repo = repo_at()
    _materialize(RecordNew(edit=_edit(name="Payments Platform")), root, repo)

    repo.refresh()
    assert TARGET in pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))


def test_it_records_the_target_the_state_the_base_and_the_edit(repo_at) -> None:  # noqa: ANN001
    root, repo = repo_at()
    result = _materialize(RecordNew(edit=_edit(name="Payments Platform")), root, repo)

    frontmatter = _changes(repo)[result.artifact_id]
    assert frontmatter["proposes-change-to"] == TARGET
    assert frontmatter["proposal-state"] == "draft"
    assert frontmatter["base-revision"] == "deadbeef"
    assert frontmatter["recorded-edit"]["fields"] == {"name": "Payments Platform"}


def test_a_dry_run_writes_nothing(repo_at) -> None:  # noqa: ANN001
    root, repo = repo_at()
    result = _materialize(RecordNew(edit=_edit(name="Payments Platform")), root, repo, dry_run=True)

    assert not result.wrote
    assert result.content is not None
    assert _changes(repo) == {}


# ── revising a draft ─────────────────────────────────────────────────────────


def test_revising_keeps_the_change_and_replaces_its_edit(repo_at) -> None:  # noqa: ANN001
    """Its identity survives, so a badge's link and a reader's bookmark still resolve."""
    root, repo = repo_at(existing_state="draft")
    result = _materialize(
        ReviseDraft(proposal_id=EXISTING, edit=_edit(name="Revised Name", notes="Written first.")),
        root, repo,
    )

    assert result.wrote
    assert result.artifact_id == EXISTING
    changes = _changes(repo)
    assert list(changes) == [EXISTING]
    assert changes[EXISTING]["recorded-edit"]["fields"]["name"] == "Revised Name"


def test_revising_leaves_the_state_and_base_alone(repo_at) -> None:  # noqa: ANN001
    root, repo = repo_at(existing_state="draft")
    _materialize(ReviseDraft(proposal_id=EXISTING, edit=_edit(name="Revised Name")), root, repo)

    frontmatter = _changes(repo)[EXISTING]
    assert frontmatter[PROPOSAL_STATE] == "draft"
    assert frontmatter["base-revision"] == "abc1234"


def test_revising_a_change_that_is_not_there_is_refused(repo_at) -> None:  # noqa: ANN001
    root, repo = repo_at()
    with pytest.raises(ValueError, match="not in the repository"):
        _materialize(ReviseDraft(proposal_id=EXISTING, edit=_edit(name="x")), root, repo)


# ── superseding one under review ─────────────────────────────────────────────


def test_superseding_writes_the_replacement_and_retires_the_original(repo_at) -> None:  # noqa: ANN001
    root, repo = repo_at(existing_state="submitted")
    result = _materialize(
        SupersedeSubmitted(
            superseded_ids=(EXISTING,),
            base_revision="abc1234",
            edit=_edit(name="Second Thoughts", notes="Written first."),
        ),
        root, repo,
    )

    assert result.wrote
    changes = _changes(repo)
    assert changes[EXISTING][PROPOSAL_STATE] == "abandoned"
    assert changes[result.artifact_id][PROPOSAL_STATE] == "draft"


def test_the_replacement_carries_the_base_the_original_was_written_against(repo_at) -> None:  # noqa: ANN001
    """Superseding is not an event upstream. A recomputed base would mark a stale change current."""
    root, repo = repo_at(existing_state="submitted")
    result = _materialize(
        SupersedeSubmitted(superseded_ids=(EXISTING,), base_revision="abc1234", edit=_edit(name="x")),
        root, repo,
    )

    assert _changes(repo)[result.artifact_id]["base-revision"] == "abc1234"


def test_the_retired_record_is_kept_rather_than_deleted(repo_at) -> None:  # noqa: ANN001
    """It is the evidence the change existed and how it ended."""
    root, repo = repo_at(existing_state="submitted")
    _materialize(
        SupersedeSubmitted(superseded_ids=(EXISTING,), base_revision="abc1234", edit=_edit(name="x")),
        root, repo,
    )

    assert (root / "model" / "common" / "proposed-change" / f"{EXISTING}.md").exists()


def test_only_the_replacement_is_live_afterwards(repo_at) -> None:  # noqa: ANN001
    """One change per artifact, which is the rule the whole outcome exists to keep."""
    root, repo = repo_at(existing_state="submitted")
    result = _materialize(
        SupersedeSubmitted(superseded_ids=(EXISTING,), base_revision="abc1234", edit=_edit(name="x")),
        root, repo,
    )

    repo.refresh()
    live = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))[TARGET]
    assert [proposal.proposal_id for proposal in live] == [result.artifact_id]


def test_a_dry_run_supersedes_nothing(repo_at) -> None:  # noqa: ANN001
    """The replacement is not written, so the original must not be retired either."""
    root, repo = repo_at(existing_state="submitted")
    _materialize(
        SupersedeSubmitted(superseded_ids=(EXISTING,), base_revision="abc1234", edit=_edit(name="x")),
        root, repo, dry_run=True,
    )

    assert _changes(repo)[EXISTING][PROPOSAL_STATE] == "submitted"


# ── a file the verifier refuses never survives ───────────────────────────────


class _Refusing:
    """A verifier that refuses whatever it is shown, standing in for a rule this test cannot trip.

    The rules that would genuinely refuse a change file are the ones the writer is built to satisfy,
    so provoking one means writing a change the writer would not write. What is under test is the
    *rollback*, not which rule fired.
    """

    def verify_entity_file(self, path: Path):  # noqa: ANN201, ARG002
        return SimpleNamespace(
            valid=False,
            issues=(SimpleNamespace(severity="error", code="E999", message="refused for this test"),),
        )


def _materialize_with(verifier, outcome, root: Path, repo: ArtifactRepository):  # noqa: ANN001, ANN202
    return materialize(
        outcome, repo=repo, engagement_root=root, verifier=verifier,
        clear_repo_caches=lambda _path: repo.refresh(), target_name="Payments Service",
        base_revision="deadbeef", dry_run=False,
    )


def test_a_refused_change_leaves_no_file_behind(repo_at) -> None:  # noqa: ANN001
    """A repository never holds a file the product's own verifier would reject — the same rollback
    the reference creator performs, and for the same reason."""
    root, repo = repo_at()
    result = _materialize_with(_Refusing(), RecordNew(edit=_edit(name="Payments Platform")), root, repo)

    assert not result.wrote
    assert not result.path.exists()
    assert _changes(repo) == {}


def test_a_refused_revision_restores_what_was_there(repo_at) -> None:  # noqa: ANN001
    """Revising rewrites an existing file, so a refusal has something to put back."""
    root, repo = repo_at(existing_state="draft")
    before = (root / "model" / "common" / "proposed-change" / f"{EXISTING}.md").read_text(encoding="utf-8")

    result = _materialize_with(
        _Refusing(), ReviseDraft(proposal_id=EXISTING, edit=_edit(name="Revised Name")), root, repo
    )

    assert not result.wrote
    assert (root / "model" / "common" / "proposed-change" / f"{EXISTING}.md").read_text(
        encoding="utf-8"
    ) == before


def test_a_refused_replacement_does_not_retire_the_original(repo_at) -> None:  # noqa: ANN001
    """The whole reason the replacement is written first."""
    root, repo = repo_at(existing_state="submitted")
    _materialize_with(
        _Refusing(),
        SupersedeSubmitted(superseded_ids=(EXISTING,), base_revision="abc1234", edit=_edit(name="x")),
        root, repo,
    )

    assert _changes(repo)[EXISTING][PROPOSAL_STATE] == "submitted"
