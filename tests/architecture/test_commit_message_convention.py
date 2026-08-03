"""Every commit subject is `Area: clause`, and the clause completes "this commit will …".

The prefix is what makes the history searchable: `git log --oneline --grep '^Assurance:'` is the only
cheap way to ask what has happened to a concern over a hundred commits, and it works exactly as long
as one concern has one name. A synonym is worse than no prefix, because it looks like it was searched.

This test exists because the convention lapsed for 81 consecutive commits without anything noticing —
it was written down nowhere and checked nowhere, so each arriving author inferred it from whatever the
last few commits happened to look like. The vocabulary below is the rule; `AGENTS.md` explains what
each area covers and when to reach for a second one.

**Why the imperative.** "REST: typed contracts for the platform reads" is a label on a diff; it does
not say whether the contracts arrived, were changed, or were removed. "REST: type the contracts for
the platform reads" reads the same way `git revert` and `git cherry-pick` present it: as an operation
that can be applied or undone.

**Range.** `v0.1.0..HEAD`, because the convention was applied to that range in full and nothing
earlier was rewritten. The test skips rather than fails when the tag is unreachable — a shallow CI
checkout or a source tarball has no history to check, and a skip there is honest where a pass would
not be. That makes this a local gate, which is where commits are written.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

#: The convention begins here. Commits before it were written under no stated rule.
_BASE = "v0.1.0"

#: Areas: layers and long-lived concerns. Adding one is a decision about the repository's vocabulary,
#: not a side effect of a change — which is why it is a literal here and a table in `AGENTS.md`.
_AREAS = frozenset({
    "REST",
    "Manifest",
    "GUI",
    "MCP",
    "Assurance",
    "Backend",
    "Viewpoints",
    "Diagram types",
    "Groups",
    "Sync",
    "Index",
    "Domain",
    "Write",
    "Quality",
    "Docs",
    "Model",
    "Tooling",
    "Consolidation",
    "Release",
})

#: An area declaration: capitalised words, then a colon and a space. Matched against each
#: semicolon-separated segment, so prose semicolons stay legal and a second area is caught.
_DECLARATION = re.compile(r"^([A-Z][A-Za-z]*(?: [a-z]+)*): (?P<clause>.+)$")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=_ROOT, capture_output=True, text=True, check=False
    )


def _subjects() -> list[tuple[str, str]]:
    """`(short hash, subject)` for every non-merge commit in range, oldest first.

    Merges are exempt: their subject is generated, and there are none in this history to prefix.
    """
    if _git("rev-parse", "--verify", f"{_BASE}^{{commit}}").returncode != 0:
        pytest.skip(f"{_BASE} is unreachable — shallow checkout or exported tree, no history to check")
    done = _git("log", "--no-merges", "--reverse", "--format=%h%x09%s", f"{_BASE}..HEAD")
    assert done.returncode == 0, done.stderr
    rows = [line.split("\t", 1) for line in done.stdout.splitlines() if "\t" in line]
    return [(h, s) for h, s in rows]


@pytest.fixture(scope="module")
def subjects() -> list[tuple[str, str]]:
    found = _subjects()
    assert found, f"no commits in {_BASE}..HEAD — the assertions below would be vacuous"
    return found


def test_every_subject_declares_an_area(subjects: list[tuple[str, str]]) -> None:
    """A subject with no prefix, or one naming an area nobody else uses."""
    offenders = []
    for short, subject in subjects:
        match = _DECLARATION.match(subject)
        if match is None:
            offenders.append(f"{short}: no `Area: ` prefix — {subject!r}")
        elif match.group(1) not in _AREAS:
            offenders.append(f"{short}: {match.group(1)!r} is not in the vocabulary — {subject!r}")
    assert offenders == [], (
        "commit subjects outside the convention:\n  "
        + "\n  ".join(offenders)
        + "\n\nAmend them (`git rebase -i` / `git commit --amend`). If an area is genuinely missing "
        "from the vocabulary, add it to `_AREAS` and to the table in `AGENTS.md` in the same commit."
    )


def test_every_clause_reads_as_an_instruction(subjects: list[tuple[str, str]]) -> None:
    """The clause completes "When applied, this commit will …", so it does not open in title case.

    Checking the mood itself needs a reader; checking the capital catches the label form that
    produced it — "REST: typed contracts …", "Assurance: An analysis record had three shapes".
    An identifier may legitimately start the clause, so only a leading capital *letter* is refused.
    """
    offenders = []
    for short, subject in subjects:
        match = _DECLARATION.match(subject)
        if match is None:
            continue  # reported by the test above
        clause = match.group("clause")
        if clause[:1].isupper():
            offenders.append(f"{short}: clause opens in title case — {subject!r}")
    assert offenders == [], (
        "commit subjects reading as labels rather than instructions:\n  "
        + "\n  ".join(offenders)
        + '\n\nRewrite so the clause completes "When applied, this commit will …".'
    )


def test_a_subject_names_at_most_two_areas(subjects: list[tuple[str, str]]) -> None:
    """Two concerns are declared with a semicolon; three mean it should have been two commits."""
    offenders = []
    for short, subject in subjects:
        declared = [
            match.group(1)
            for segment in subject.split("; ")
            if (match := _DECLARATION.match(segment)) is not None
        ]
        if len(declared) > 2:
            offenders.append(f"{short}: {declared} — {subject!r}")
    assert offenders == [], (
        "commit subjects declaring more than two areas:\n  "
        + "\n  ".join(offenders)
        + "\n\nSplit the commit. The prefix records the concern; a list of three records none."
    )


def test_a_second_area_comes_from_the_same_vocabulary(subjects: list[tuple[str, str]]) -> None:
    """A trailing `; Foo: …` is a declaration too, and is held to the same set.

    A semicolon used as punctuation is untouched — it is only a declaration when what follows looks
    like one, which is what keeps this from policing prose.
    """
    offenders = []
    for short, subject in subjects:
        for segment in subject.split("; ")[1:]:
            match = _DECLARATION.match(segment)
            if match is not None and match.group(1) not in _AREAS:
                offenders.append(f"{short}: {match.group(1)!r} — {subject!r}")
    assert offenders == [], (
        "second areas outside the vocabulary:\n  " + "\n  ".join(offenders)
    )
