"""`CHANGELOG.md` stays a summary, and every release it names has its detail beside it.

The changelog is split in two on purpose. The main file answers "what changed and what must I do",
compressed enough that an adopter finishes it; `changelog-assets/<version>-detail.md` answers "why, and
exactly what" for a maintainer or a migrating consumer. Both are the release record — the detail is
moved, not dropped.

A two-file arrangement drifts in one direction, which is what this holds: a release gets a section and
no detail file (or the reverse), or the summary quietly regrows into the thing it was split out of. The
route map next door is held against `_retired.py` the same way, by
`test_changelog_route_mapping.py`.

`0.1.0` is exempt: it predates the split and its section is five bullet points, which is already a
summary and has no detail to move.

**A detail file is named for its release, and covers the range since the previous one.**
`0.2.0-detail.md` is every change since `v0.1.0`. There is no "unreleased" detail file: a release that
has not been tagged is still that release, and inventing a boundary for it produced a section and a file
named for a version nothing would ever ship. `git tag -l` is what says whether a version has shipped —
`pyproject.toml`'s version and a date in a heading do not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG = _ROOT / "CHANGELOG.md"
_ASSETS = _ROOT / "changelog-assets"

#: Sections that predate the split and carry no detail file. Shrink-only in spirit: a new release
#: belongs in the arrangement, not in this set.
_WITHOUT_DETAIL = frozenset({"0.1.0"})

#: The main file is a summary. The bound is generous — it is not a style rule, it catches the summary
#: growing back into the detail it replaced. It was 164 lines before the split, of which 130 were one
#: release; a summary of three releases sits near 100.
_SUMMARY_LINE_BUDGET = 200


def _changelog() -> str:
    return _CHANGELOG.read_text(encoding="utf-8")


def _release_headings() -> list[str]:
    """Every version a section names, as it appears in the heading."""
    return re.findall(r"^## \[([^\]]+)\]", _changelog(), flags=re.M)


def test_the_changelog_names_releases_at_all() -> None:
    """The precondition: an empty parse would make every assertion below vacuous."""
    headings = _release_headings()
    assert len(headings) >= 2, headings
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in headings), (
        f"every section names a version: {headings}. A placeholder heading has no detail file to pair "
        "with, and 'unreleased' is a property of a version rather than a version of its own — the "
        "heading carries it as its date."
    )


def test_every_release_section_has_a_detail_file() -> None:
    """A section with no detail file means the detail was compressed away rather than moved."""
    missing = []
    for version in _release_headings():
        if version in _WITHOUT_DETAIL:
            continue
        name = f"{version}-detail.md"
        if not (_ASSETS / name).is_file():
            missing.append(f"{version} → changelog-assets/{name}")
    assert missing == [], (
        f"release sections with no detail file: {missing}. The main changelog is a summary; the detail "
        "belongs beside it, not deleted."
    )


def test_every_detail_file_has_a_release_section() -> None:
    """The other direction, so a detail file cannot outlive the release it documents.

    A detail file for a version the changelog does not name is a file nobody reads, describing a
    version nobody ships — which is what a placeholder name produces.
    """
    headings = set(_release_headings())
    orphans = []
    for path in sorted(_ASSETS.glob("*-detail.md")):
        version = path.name[: -len("-detail.md")]
        if version not in headings:
            orphans.append(path.name)
    assert orphans == [], (
        f"detail files with no release section in CHANGELOG.md: {orphans}. Rename both halves together, "
        "or add the section."
    )


def test_every_release_section_links_its_detail_file() -> None:
    """A detail file nobody links to is a detail file nobody finds."""
    text = _changelog()
    sections = re.split(r"^## \[", text, flags=re.M)[1:]
    unlinked = []
    for section in sections:
        version = section[: section.index("]")]
        if version in _WITHOUT_DETAIL:
            continue
        if f"changelog-assets/{version}-detail.md" not in section:
            unlinked.append(version)
    assert unlinked == [], f"release sections not linking their detail file: {unlinked}"


def test_the_main_changelog_stays_a_summary() -> None:
    counted = len([line for line in _changelog().splitlines() if line.strip()])
    assert counted <= _SUMMARY_LINE_BUDGET, (
        f"CHANGELOG.md is {counted} non-blank lines, past the {_SUMMARY_LINE_BUDGET}-line budget. Move "
        "the per-item reasoning into the release's detail file and leave the summary and the action."
    )


@pytest.mark.parametrize("name", ["0.2.0-detail.md"])
def test_a_detail_file_points_back_at_the_summary(name: str) -> None:
    """Read on its own, a detail file has to say where the short version is.

    Someone arrives here from a search result as often as from the link.
    """
    text = (_ASSETS / name).read_text(encoding="utf-8")
    assert "CHANGELOG.md" in text, name
