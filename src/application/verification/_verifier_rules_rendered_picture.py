"""What a diagram's rendered picture gets wrong that its body cannot show (W370–W374).

The syntax check already renders every diagram to find out whether PlantUML accepts it, and threw
the picture away. This reads that picture before it goes, so the checks cost a parse and no render:

* **W371** — a relation drawn through an element it does not join;
* **W372** — two shapes drawn over each other;
* **W373** — a label wider than the shape it labels;
* **W374** — a box drawn over a shape that is not inside it;
* **W370** — the picture stated the kind this project reads and could not be read, so none of the
  four were decided. Reported rather than passed over, because a check that silently stopped
  examining pictures looks exactly like a repository of clean ones.

**Warnings, and why not errors.** The layout engine places the shapes, not the author, so a write
refused over where GraphViz put a line would be a write the author cannot always repair. Measured
when the rule was written: none of the four occurs in any picture PlantUML lays out for this
project's own model. They are for the pictures that do go wrong, and for a layout an author states.

**Crossings and the worst detour are not findings.** They are counted and carried in the `details`
of whatever this reports, to point the eye. A diagram that only crosses lines reports nothing: the
verifier knows two severities, and a warning on every dense view is a warning nobody reads.

One finding per kind per diagram, naming the first few places and counting the rest, so a picture
with a dozen overlaps reads as one statement about that picture rather than a dozen about its parts.

W375–W379 and E370–E379 are left for the rules of a stated layout.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.application.verification.artifact_verifier_types import Issue, Severity
from src.domain.diagrams.layout.picture_checks import (
    PictureDefect,
    PictureFinding,
    PictureReport,
    check_picture,
)
from src.domain.diagrams.layout.rendered_picture import NotReadable, RenderedPicture

PictureReader = Callable[[str], RenderedPicture | NotReadable]

#: How many places a message names before it counts the rest. All of them are in `details`.
_NAMED_IN_MESSAGE = 3

UNREAD_PICTURE_CODE = "W370"

_CODE_OF: Mapping[PictureDefect, str] = {
    PictureDefect.RELATION_THROUGH_ELEMENT: "W371",
    PictureDefect.SHAPES_OVERLAP: "W372",
    PictureDefect.LABEL_WIDER_THAN_SHAPE: "W373",
    PictureDefect.BOX_OVER_NON_MEMBER: "W374",
}


class RenderedPictureChecks(Protocol):
    """What the syntax check hands a rendered picture to, while it still has it."""

    def check(self, svg: str, loc: str) -> list[Issue]: ...


def _called(picture: RenderedPicture, alias: str) -> str:
    """What a shape is called on the picture; its alias where it carries no label, as a junction does."""
    label = picture.label_of(alias)
    return f"«{label}»" if label else f"the unlabelled shape {alias}"


def _place(picture: RenderedPicture, finding: PictureFinding) -> str:
    names = [_called(picture, alias) for alias in finding.shapes]
    if finding.defect is PictureDefect.RELATION_THROUGH_ELEMENT:
        return f"the relation between {names[0]} and {names[1]} through {names[2]}"
    if finding.defect is PictureDefect.LABEL_WIDER_THAN_SHAPE:
        return names[0]
    if finding.defect is PictureDefect.BOX_OVER_NON_MEMBER:
        return f"the box {names[0]} over {names[1]}"
    return f"{names[0]} and {names[1]}"


def _advisory(report: PictureReport) -> dict[str, object]:
    detour = report.worst_detour
    return {
        "crossings": report.crossings,
        "worst_detour": None
        if detour is None
        else {"between": list(detour.ends), "times_the_direct_line": round(detour.ratio, 2)},
    }


def _issue(
    picture: RenderedPicture, report: PictureReport, defect: PictureDefect, found: Sequence[PictureFinding], loc: str
) -> Issue:
    places = [_place(picture, finding) for finding in found]
    named = "; ".join(places[:_NAMED_IN_MESSAGE])
    rest = len(places) - _NAMED_IN_MESSAGE
    return Issue(
        Severity.WARNING,
        _CODE_OF[defect],
        f"The rendered picture has {defect.value}, {len(places)} time(s): {named}"
        + (f"; and {rest} more" if rest > 0 else "")
        + ".",
        loc,
        details={
            "places": [{"shapes": list(finding.shapes), "described": place}
                       for finding, place in zip(found, places, strict=True)],
            "advisory": _advisory(report),
        },
    )


def picture_issues(picture: RenderedPicture, loc: str) -> list[Issue]:
    """One warning per kind of defect the geometry of *picture* decides."""
    report = check_picture(picture)
    return [
        _issue(picture, report, defect, found, loc)
        for defect in PictureDefect
        if (found := report.of(defect))
    ]


@dataclass(frozen=True)
class RenderedPictureRule:
    """Reads a rendered picture through *read* and reports what its geometry decides.

    The reader is given rather than imported: reading a renderer's SVG is infrastructure, and the
    verifier's composition root is what joins the two.
    """

    read: PictureReader

    def check(self, svg: str, loc: str) -> list[Issue]:
        picture = self.read(svg)
        if isinstance(picture, RenderedPicture):
            return picture_issues(picture, loc)
        if not picture.stated_the_kind_read:
            return []
        return [
            Issue(
                Severity.WARNING,
                UNREAD_PICTURE_CODE,
                f"The rendered picture could not be read, so its geometry was not checked: it holds {picture.met}.",
                loc,
            )
        ]


#: Where a batch renders each picture: a directory of this name beside the source it was drawn from.
PICTURE_BESIDE_ITS_SOURCE = "rendered-picture"


def require_a_directory_each(paths: Sequence[Path]) -> None:
    """Refuse a batch in which two sources share a directory, where their pictures would too."""
    if len({path.parent for path in paths}) != len(paths):
        raise ValueError(
            "pictures are rendered beside their sources, so each source needs a directory of its own"
        )


def add_picture_issues(issues_by_path: dict[Path, list[Issue]], checks: RenderedPictureChecks) -> None:
    """Add what *checks* say of each picture a batch rendered beside its source.

    Only for a source with no finding yet. PlantUML draws a refused body too — as a picture of its
    error message — and reading that would report on a picture nobody asked for.
    """
    for path, issues in issues_by_path.items():
        if not issues:
            issues.extend(issues_for_picture_in(path.parent / PICTURE_BESIDE_ITS_SOURCE, checks, str(path)))


def issues_for_picture_in(directory: Path, checks: RenderedPictureChecks, loc: str) -> list[Issue]:
    """What *checks* say of the one picture rendered into *directory*.

    Nothing where the directory holds no picture — the render failed, and the syntax finding says so
    — and nothing where it holds several: a file that draws more than one diagram has no one picture
    to speak of.
    """
    try:
        pictures = sorted(directory.glob("*.svg"))
        if len(pictures) != 1:
            return []
        svg = pictures[0].read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return checks.check(svg, loc)
