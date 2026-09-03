"""Advancing a proposal's state changes one word and leaves the rest of the file alone.

The field is rewritten in place rather than by re-rendering: only the YAML region is replaced, so
both fences, the body and the file's line endings survive a transition that is supposed to change one
word. A rewrite that reformats everything makes the diff useless for review and risks losing whatever
the renderer does not know about — which for an internal artifact is most of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.proposal_lifecycle import (
    ProposalTransitionRefused,
    mark_proposal_state,
)

PROPOSAL_ID = "PCH@1780000000.aaaaaaa.rename-it"

SOURCE = (
    "---\n"
    f"artifact-id: {PROPOSAL_ID}\n"
    "artifact-type: proposed-change\n"
    "proposes-change-to: APP@1780000001.bbbbbbb.payments-service\n"
    "proposal-state: submitted\n"
    "base-revision: abc1234\n"
    "recorded-edit:\n"
    "  kind: entity\n"
    "  artifact-id: APP@1780000001.bbbbbbb.payments-service\n"
    "  fields:\n"
    "    name: Payments Platform\n"
    "---\n"
    "\n"
    "<!-- §content -->\n"
    "\n"
    "## Rename it\n"
    "\n"
    "A note the renderer knows nothing about.\n"
)


@pytest.fixture()
def proposal(tmp_path: Path) -> Path:
    path = tmp_path / f"{PROPOSAL_ID}.md"
    path.write_text(SOURCE, encoding="utf-8")
    return path


def test_the_state_is_recorded(proposal: Path) -> None:
    changed = mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="integrated")

    assert changed
    assert "proposal-state: integrated" in proposal.read_text(encoding="utf-8")
    assert "proposal-state: submitted" not in proposal.read_text(encoding="utf-8")


def test_the_body_survives_untouched(proposal: Path) -> None:
    """Everything after the closing fence, including what no renderer would reproduce."""
    mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="integrated")
    written = proposal.read_text(encoding="utf-8")

    assert "A note the renderer knows nothing about." in written
    assert "<!-- §content -->" in written
    assert written.count("---\n") == SOURCE.count("---\n")


def test_the_rest_of_the_frontmatter_survives(proposal: Path) -> None:
    mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="integrated")
    written = proposal.read_text(encoding="utf-8")

    for kept in ("proposes-change-to:", "base-revision: abc1234", "recorded-edit:", "name: Payments Platform"):
        assert kept in written, kept


def test_a_proposal_already_in_that_state_is_left_byte_identical(proposal: Path) -> None:
    """The sweep runs on every startup. Rewriting a file per boot makes the repository look dirty to
    the next status read, which blocks a save for no reason."""
    before = proposal.read_bytes()

    changed = mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="submitted")

    assert not changed
    assert proposal.read_bytes() == before


def test_the_transition_is_idempotent(proposal: Path) -> None:
    assert mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="integrated")
    after_first = proposal.read_bytes()

    assert not mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="integrated")
    assert proposal.read_bytes() == after_first


def test_a_state_outside_the_vocabulary_is_refused(proposal: Path) -> None:
    with pytest.raises(ProposalTransitionRefused, match="not a proposal state"):
        mark_proposal_state(proposal, artifact_id=PROPOSAL_ID, state="merged")  # type: ignore[arg-type]

    assert "proposal-state: submitted" in proposal.read_text(encoding="utf-8")


def test_a_file_with_no_frontmatter_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "not-an-artifact.md"
    path.write_text("Just prose.\n", encoding="utf-8")

    with pytest.raises(ProposalTransitionRefused, match="no frontmatter"):
        mark_proposal_state(path, artifact_id=PROPOSAL_ID, state="integrated")

    assert path.read_text(encoding="utf-8") == "Just prose.\n"
