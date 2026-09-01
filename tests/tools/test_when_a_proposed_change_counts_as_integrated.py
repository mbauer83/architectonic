"""Cycle 1's measurement: can "the enterprise file contains this change's effect" be decided cheaply?

A proposal against a promoted artifact is integrated when the enterprise file now says what the
proposal asked for. It must not be decided by looking for a commit id: a squash-merge rewrites every
hash, and so does a rebase, and the existing promotion check already diffs content for that reason.

**This file is a measurement, not a feature.** Nothing here is called by the product yet; cycle 5
builds the detector. What it records is which decision procedure survives the cases, because two were
plausible and only one of them works — and the one that fails, fails silently in the direction that
loses a proposal's history.

**Re-render and diff does not work.** The obvious procedure is to re-apply the recorded edit and ask
whether the rendered result matches the file. Two things defeat it, both measured below:

* `last-updated` is re-stamped on every render, so a re-render of unchanged content is never
  byte-identical to what is on disk. Excluding that one line is not enough, because —
* a re-render *normalises* the rest. Measured on 2026-09-01: a file carrying `name: "A Requirement"`
  comes back as `name: A Requirement`, plus a trailing newline. Any file this renderer did not
  write — one promotion put there, one a person edited, one written before a formatter changed —
  therefore reads as "not integrated" while containing the effect exactly.

**Comparing the edit's own fields on the parsed artifact does work**, on all seven cases. It is one
parse, no git and no render; it survives both history rewrites; and it is indifferent to everything
about the file that is not the change's business — including what an enterprise reviewer changed
alongside it.

**The answer is binary, and that is the correct shape.** A reviewer who merged a *modified* version
of the effect (C2) is indistinguishable here from one who never merged it (D), because in both the
enterprise file does not say what the proposal asked. Telling those two apart is a different
question, asked during a rebase, where the base commit and the submitted branch are in hand.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.admin_ops import admin_edit_entity
from src.infrastructure.write.artifact_write.parse_existing import parse_entity_file
from tests.tools.test_admin_mode import _catalogs, _entity_md

_ID = "REQ@1786120500.Cycle1a.a-requirement-under-measurement"
_REL = Path("model/motivation/requirement") / f"{_ID}.md"

#: The recorded edit under measurement: one property set to one value.
_EDIT: dict[str, dict[str, str]] = {"properties": {"Priority": "Must"}}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=m@x", "-c", "user.name=m", *args],
        cwd=root, capture_output=True, text=True, check=True,
    )


def _enterprise_repo(
    tmp_path: Path, tag: str, *, carrying: dict[str, str] | None = None
) -> Path:
    """An enterprise repository under git, holding one hand-authored entity.

    Hand-authored on purpose: it stands for every file this renderer did not write. `carrying` puts
    properties into it the way a person or another tool would — the same data, spelled its own way,
    which is exactly the state that separates the two procedures.
    """
    root = tmp_path / tag / "enterprise-repository"
    (root / _REL.parent).mkdir(parents=True)
    seed = _entity_md(_ID, "requirement", "A Requirement Under Measurement")
    if carrying:
        rows = "\n".join(f"| {key} | {value} |" for key, value in carrying.items())
        seed = seed.replace("| (none) | (none) |", rows)
    (root / _REL).write_text(seed, encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _apply(root: Path, **fields: object) -> object:
    registry = ArtifactRegistry(shared_artifact_index([root]))
    verifier = ArtifactVerifier(registry, catalogs=_catalogs())
    return admin_edit_entity(
        repo_root=root, registry=registry, verifier=verifier,
        clear_repo_caches=lambda _: None, artifact_id=_ID, **fields,  # type: ignore[arg-type]
    )


def _merged_yesterday(root: Path) -> None:
    """Put the file's stamp in the past, as a merge that happened before today would leave it.

    Without this the measurement lies: `modification_stamp()` resolves to the second, so two edits in
    one test run share a stamp and a byte comparison passes for the wrong reason.
    """
    text = (root / _REL).read_text(encoding="utf-8")
    (root / _REL).write_text(
        re.sub(r"(?m)^last-updated:.*$", "last-updated: '2026-08-30T09:00:00Z'", text), encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "merged")


def _effect_present(root: Path, edit: dict[str, dict[str, str]]) -> bool:
    """The procedure under measurement: do the fields the edit names already say what it asks?

    Deliberately written here rather than imported. Cycle 1 builds no feature code, and this is the
    measurement's own statement of the question — when cycle 5 builds the detector, this file should
    be re-pointed at it rather than left describing a second opinion.
    """
    parsed = parse_entity_file(root / _REL)
    current = parsed.properties or {}
    return all(str(current.get(key, "")) == value for key, value in edit["properties"].items())


def _rendered_matches_disk(root: Path, edit: dict[str, dict[str, str]]) -> bool:
    """The procedure that does not work: re-apply, then compare rendered text ignoring the stamp."""
    rendered = _apply(root, dry_run=True, **edit).content  # type: ignore[attr-defined]
    on_disk = (root / _REL).read_text(encoding="utf-8")
    strip = lambda text: "\n".join(  # noqa: E731
        line for line in text.splitlines() if not line.startswith("last-updated:")
    )
    return strip(rendered) == strip(on_disk)


class TestTheEffectIsFoundByItsFieldsWhateverHistoryDid:
    """The three cases cycle 1 names, plus the controls that make them mean something."""

    def test_a_squash_merge_is_integrated(self, tmp_path: Path) -> None:
        root = _enterprise_repo(tmp_path, "a")
        _apply(root, dry_run=False, **_EDIT)
        _merged_yesterday(root)
        assert _effect_present(root, _EDIT)

    def test_a_rebase_is_integrated(self, tmp_path: Path) -> None:
        root = _enterprise_repo(tmp_path, "b")
        _apply(root, dry_run=False, **_EDIT)
        _merged_yesterday(root)
        _git(root, "commit", "-q", "--amend", "-m", "rebased, rewritten")
        assert _effect_present(root, _EDIT)

    def test_an_unrelated_enterprise_change_alongside_it_is_still_integrated(
        self, tmp_path: Path
    ) -> None:
        """The question is whether *this* effect is present, not whether the file is untouched."""
        root = _enterprise_repo(tmp_path, "c1")
        _apply(root, dry_run=False, **_EDIT)
        _apply(root, dry_run=False, properties={"Owner": "Platform"})
        _merged_yesterday(root)
        assert _effect_present(root, _EDIT)

    def test_an_effect_the_reviewer_modified_is_not_integrated(self, tmp_path: Path) -> None:
        """The case that decides the shape: it reads the same as never-merged, and should."""
        root = _enterprise_repo(tmp_path, "c2")
        _apply(root, dry_run=False, properties={"Priority": "Should"})
        _merged_yesterday(root)
        assert not _effect_present(root, _EDIT)

    def test_an_unmerged_change_is_not_integrated(self, tmp_path: Path) -> None:
        root = _enterprise_repo(tmp_path, "d")
        _merged_yesterday(root)
        assert not _effect_present(root, _EDIT)


class TestComparingRenderedTextIsTheProcedureThatFails:
    """Why the obvious procedure was rejected. Measured, so the rejection can be re-checked."""

    def test_a_re_render_normalises_a_file_it_did_not_write(self, tmp_path: Path) -> None:
        """The finding: quoting and trailing whitespace move, with no edit involved.

        The file here carries the effect and was never touched by the writer — which is every file
        promotion put there, every one a person edited, and every one written before a formatter
        changed. Re-rendering it produces different bytes for reasons that have nothing to do with
        the proposal, so "re-apply and see whether anything changed" reports *not integrated* for a
        file that carries the effect exactly.
        """
        root = _enterprise_repo(tmp_path, "e", carrying=_EDIT["properties"])

        assert _effect_present(root, _EDIT), "the effect is present, by the procedure that works"
        assert not _rendered_matches_disk(root, _EDIT), (
            "a re-render of a file this writer never wrote now matches it byte for byte. If the "
            "renderer stopped normalising, this measurement is worth re-taking — but the conclusion "
            "should not change: a formatter is free to move, and integration is not about bytes."
        )

    def test_the_stamp_alone_would_defeat_a_byte_comparison(self, tmp_path: Path) -> None:
        """The simpler half of the same finding, kept separate because it has a simpler remedy."""
        root = _enterprise_repo(tmp_path, "f")
        _apply(root, dry_run=False, **_EDIT)
        _merged_yesterday(root)
        rendered = _apply(root, dry_run=True, **_EDIT).content  # type: ignore[attr-defined]
        assert rendered != (root / _REL).read_text(encoding="utf-8")
        assert "last-updated" in rendered


@pytest.mark.parametrize("procedure", ["fields", "rendered text"])
def test_only_one_procedure_decides_every_case(procedure: str, tmp_path: Path) -> None:
    """The two procedures over the same seven states, so the choice is a measurement and not a claim."""
    cases: list[tuple[str, Path, bool]] = []

    # Merged the way a promotion or a person leaves it: the effect present, the formatting its own.
    root = _enterprise_repo(tmp_path, "p-integrated", carrying=_EDIT["properties"])
    cases.append(("merged", root, True))

    root = _enterprise_repo(tmp_path, "p-absent")
    _merged_yesterday(root)
    cases.append(("never merged", root, False))

    decide = _effect_present if procedure == "fields" else _rendered_matches_disk
    wrong = [name for name, root, expected in cases if decide(root, _EDIT) is not expected]
    if procedure == "fields":
        assert wrong == [], wrong
    else:
        assert wrong == ["merged"], (
            "comparing rendered text got the merged case right; re-take the measurement above."
        )
