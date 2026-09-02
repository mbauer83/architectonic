"""Every artifact kind the enterprise repository holds can be edited through the admin surface.

Promotion puts three kinds there — entities, documents and diagrams. Only the first could be edited
afterwards. A document promoted to the enterprise repository, which is what a shared standard is,
could be created and deleted and nothing in between; so could a diagram.

That is the gap this closes, and the way it is closed is the point. `edit_document` and
`edit_diagram` never depended on which repository they wrote: every path they touch is derived from
a `repo_root` they are handed, and their one engagement-specific line was the root assertion. Making
that assertion a parameter turns them into the same computation under either authority. The
alternative — a second copy per kind — is what the entity edit had, and its copy had quietly lost
`attribute_types` and `specializations`.

So these assertions are about composition as much as capability: each admin edit is checked to reach
the same computation, and to refuse the wrong repository, which is the one thing the authority
decides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.admin_ops import (
    admin_edit_diagram,
    admin_edit_document,
)
from src.infrastructure.write.artifact_write.boundary import (
    assert_engagement_write_root,
    assert_enterprise_write_root,
)


@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    (root / "model").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    return root


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "docs").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


class TestTheTwoAuthoritiesAreTheOneDifference:
    """Which root assertion runs decides which repository, and nothing else about the computation."""

    def test_each_authority_accepts_only_its_own_repository(
        self, enterprise_root: Path, engagement_root: Path
    ) -> None:
        assert_enterprise_write_root(enterprise_root)
        assert_engagement_write_root(engagement_root)

        with pytest.raises(ValueError, match="enterprise"):
            assert_enterprise_write_root(engagement_root)
        with pytest.raises(ValueError, match="enterprise"):
            assert_engagement_write_root(enterprise_root)

    def test_an_admin_edit_refuses_an_engagement_root(self, engagement_root: Path) -> None:
        """The guard is the first thing each does, so a mis-pointed root fails before any read."""
        with pytest.raises(ValueError, match="enterprise"):
            admin_edit_document(
                repo_root=engagement_root, verifier=None, clear_repo_caches=lambda _: None,  # type: ignore[arg-type]
                artifact_id="STD@1.aaaaaa.x", dry_run=True,
            )
        with pytest.raises(ValueError, match="enterprise"):
            admin_edit_diagram(
                repo_root=engagement_root, verifier=None, clear_repo_caches=lambda _: None,  # type: ignore[arg-type]
                artifact_id="DGR@1.aaaaaa.x", dry_run=True,
            )


class TestTheAdminEditsAreProjectionsOfTheEngagementOnes:
    """Composition, asserted on the signatures rather than trusted to a docstring.

    Every field an admin edit offers must be a field the engagement computation accepts, or it is
    not the same computation — it is a second one that happens to look similar, which is the shape
    this stage exists to remove.
    """

    def test_the_document_edit_offers_nothing_the_engagement_one_lacks(self) -> None:
        import inspect

        from src.infrastructure.write.artifact_write.document import edit_document

        offered = set(inspect.signature(admin_edit_document).parameters)
        accepted = set(inspect.signature(edit_document).parameters) - {"assert_write_root"}
        assert offered <= accepted, sorted(offered - accepted)

    def test_the_diagram_edit_offers_nothing_the_engagement_one_lacks(self) -> None:
        import inspect

        from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram

        offered = set(inspect.signature(admin_edit_diagram).parameters)
        accepted = set(inspect.signature(edit_diagram).parameters) - {"assert_write_root"}
        assert offered <= accepted, sorted(offered - accepted)

    def test_neither_admin_edit_offers_a_relocation(self) -> None:
        """`group` moves a file between directories, which the admin surface cannot do for any kind."""
        import inspect

        assert "group" not in inspect.signature(admin_edit_document).parameters
        assert "group" not in inspect.signature(admin_edit_diagram).parameters
