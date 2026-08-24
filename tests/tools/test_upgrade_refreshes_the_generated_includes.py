"""`arch-repair upgrade` leaves no generated ArchiMate include behind.

`_archimate-stereotypes.puml`, `_archimate-glyphs.puml` and `_archimate-relations.puml` are
*generated* files committed into a repository: every diagram `!include`s them, and their content is
the ontology's declarations rendered into skinparams and macros. So when a release changes a
declaration, the change reaches an existing repository only when those files are rewritten.

Nothing rewrote them on upgrade. `arch-init` regenerates them and CI checks them, and
`arch-repair upgrade` — the command whose whole job is bringing a repository to the current
version — did not. So 0.7.1's grouping notation, and every ontology appearance change before it,
stopped at the repository boundary: the ontology said dashed and unfilled, and the file every diagram
includes still said filled with a solid border.

Not an upgrade *step*: a step's content comes from the domain, and this content is generated from the
registry, which an application-layer step may not reach. The CLI is the composition root that already
does exactly this in `arch-init`, so it does it here too — one call, after the steps have applied,
because a step may itself change what the generator would emit.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _includes(root: Path) -> list[Path]:
    return sorted((root / "diagram-catalog").glob("_archimate-*.puml"))


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repository whose generated includes are stale, spelled the way a real one is."""
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    catalog = root / "diagram-catalog"
    catalog.mkdir(parents=True)
    (root / ".arch-repo").mkdir()
    for name in ("_archimate-stereotypes.puml", "_archimate-glyphs.puml", "_archimate-relations.puml"):
        (catalog / name).write_text("' stale\nskinparam rectangle<<grouping>> {\n  BorderStyle solid\n}\n")
    return root


class TestTheRefresh:
    def test_it_rewrites_every_generated_include(self, repo: Path) -> None:
        from src.infrastructure.cli.arch_repair_upgrade import refresh_generated_includes

        before = {p.name: p.read_text() for p in _includes(repo)}
        refreshed = refresh_generated_includes([repo])

        assert refreshed, "nothing reported as refreshed"
        for path in _includes(repo):
            assert path.read_text() != before[path.name], f"{path.name} was not rewritten"

    def test_the_stereotype_file_carries_the_current_declaration(self, repo: Path) -> None:
        """The reason this exists: 0.7.1's grouping notation has to reach an upgraded repository."""
        from src.infrastructure.cli.arch_repair_upgrade import refresh_generated_includes

        refresh_generated_includes([repo])
        content = (repo / "diagram-catalog" / "_archimate-stereotypes.puml").read_text()

        marker = "skinparam rectangle<<grouping>> {"
        assert marker in content
        block = content[content.index(marker):content.index("}", content.index(marker))]
        assert "BorderStyle dashed" in block, f"the refreshed file still draws a filled grouping: {block!r}"

    def test_it_is_idempotent(self, repo: Path) -> None:
        from src.infrastructure.cli.arch_repair_upgrade import refresh_generated_includes

        refresh_generated_includes([repo])
        once = {p.name: p.read_text() for p in _includes(repo)}
        refresh_generated_includes([repo])

        assert {p.name: p.read_text() for p in _includes(repo)} == once

    def test_a_root_with_no_catalog_is_left_alone_rather_than_failing(self, tmp_path: Path) -> None:
        """An upgrade runs over every configured root, and one of them may be a repository that has
        no diagram catalogue at all. That must not fail the run."""
        from src.infrastructure.cli.arch_repair_upgrade import refresh_generated_includes

        bare = tmp_path / "bare"
        bare.mkdir()

        assert refresh_generated_includes([bare]) == []
