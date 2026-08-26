"""Every captured figure in `docs/media` carries its provenance, and every record names a real file.

`docs/media/manifest.json` records how each figure was produced — the route, the parameters, the
viewport, the capture tool and the file's digest. It is written by the media suite, which is **not in
CI**: nothing else looks at it, so a manifest that loses entries ships silently.

**It has lost them twice, two different ways.** The first was a preflight reset guarded on the media
project being *configured* rather than selected, which cleared the file to `[]` on any run of another
project — forty-three figures' provenance, gone. The fix truncates at the first capture instead, so a
run that captures nothing never touches the file. That is correct for a whole-project run and wrong
for a filtered one: `playwright test --project=media -g "one test"` captures something, truncates, and
writes back the single entry it took. Thirty-five records replaced by one, with the figures themselves
untouched and nothing to notice.

So the invariant lives here rather than in the writer's guard. Hand-authored figures — diagrams drawn
for the docs rather than screenshotted from the product — have no capture to record and are named
below; everything else must be accounted for.
"""

from __future__ import annotations

import json
from pathlib import Path

_MEDIA = Path(__file__).resolve().parents[2] / "docs" / "media"
_MANIFEST = _MEDIA / "manifest.json"

#: Figures authored by hand rather than captured from the running product, so no capture records them.
#: A file joins this set only when it is genuinely drawn; a *captured* figure listed here would hide
#: exactly the loss this gate exists to catch.
_HAND_AUTHORED = frozenset({
    "assurance-why-motivation-chain.svg",
    "motivation-core-trade-off.svg",
    "motivation-forces.svg",
    "motivation-goals-outcomes.svg",
    "motivation-story.svg",
    "scratchpad-hero.png",
})

_FIGURE_SUFFIXES = (".png", ".gif", ".svg")


def _recorded() -> dict[str, dict]:
    entries = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return {entry["output_path"].rsplit("/", 1)[-1]: entry for entry in entries}


def _figures() -> set[str]:
    return {p.name for p in _MEDIA.iterdir() if p.suffix in _FIGURE_SUFFIXES}


def test_every_captured_figure_has_its_provenance() -> None:
    """The direction that catches a truncated manifest: figures on disk with no record."""
    missing = sorted(_figures() - _HAND_AUTHORED - set(_recorded()))

    assert missing == [], (
        "these figures have no provenance record. A filtered media run rewrites the manifest with "
        "only what it captured — re-shoot the whole set with `npm run media` rather than adding "
        f"entries by hand: {missing}"
    )


def test_every_record_names_a_figure_that_exists() -> None:
    """The other direction: a record left behind by a figure that was renamed or removed."""
    stranded = sorted(set(_recorded()) - _figures())

    assert stranded == [], (
        f"these records name figures that are not in docs/media: {stranded}"
    )


def test_a_hand_authored_figure_is_not_also_captured() -> None:
    """The allowlist is for figures no capture produces. One that *is* captured would be excused from
    the check above for no reason, and its provenance could then go missing unnoticed."""
    both = sorted(_HAND_AUTHORED & set(_recorded()))

    assert both == [], (
        f"these are recorded as captures, so they do not belong in the hand-authored set: {both}"
    )


def test_the_allowlist_names_only_figures_that_are_there() -> None:
    """A name left in the set after its figure went keeps a hole open for a future figure of that
    name to fall through."""
    absent = sorted(_HAND_AUTHORED - _figures())

    assert absent == [], f"these are excused but no longer exist: {absent}"


def test_each_record_carries_what_makes_it_provenance() -> None:
    """A record with no digest or no route is a row, not evidence."""
    thin = sorted(
        name for name, entry in _recorded().items()
        if not entry.get("sha256") or not entry.get("output_path")
    )

    assert thin == [], f"these records carry no digest or no path: {thin}"
