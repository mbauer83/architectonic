#!/usr/bin/env python3
"""Export rendered self-model diagrams used by the public docs.

Usage:
    uv run tools/docs/export_doc_diagrams.py             # copy into docs/media/
    uv run tools/docs/export_doc_diagrams.py --check     # fail if a copy is stale
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagramExport:
    source: str
    target: str


EXPORTS: tuple[DiagramExport, ...] = (
    DiagramExport(
        "engagements/ENG-ARCH-REPO/architecture-repository/diagram-catalog/rendered/"
        "motivation-narrative/ARC@1777455142.cFB8Hs.the-forces-shaping-this-system.svg",
        "docs/media/motivation-forces.svg",
    ),
    DiagramExport(
        "engagements/ENG-ARCH-REPO/architecture-repository/diagram-catalog/rendered/"
        "motivation-narrative/ARC@1777452513.d8jG_4.what-we-are-trying-to-achieve.svg",
        "docs/media/motivation-goals-outcomes.svg",
    ),
    DiagramExport(
        "engagements/ENG-ARCH-REPO/architecture-repository/diagram-catalog/rendered/"
        "motivation-narrative/ARC@1780220700.Un4jQZ.the-story-in-one-view.svg",
        "docs/media/motivation-story.svg",
    ),
    DiagramExport(
        "engagements/ENG-ARCH-REPO/architecture-repository/diagram-catalog/rendered/"
        "motivation-narrative/"
        "ARC@1784849983.W6j62G.the-core-trade-off-local-autonomy-and-enterprise-adaptability.svg",
        "docs/media/motivation-core-trade-off.svg",
    ),
    DiagramExport(
        "engagements/ENG-ARCH-REPO/architecture-repository/diagram-catalog/rendered/"
        "assurance/ARC@1780656714.9qoEQO.why-assurance-motivation-chain.svg",
        "docs/media/assurance-why-motivation-chain.svg",
    ),
)


def export_diagrams(repo_root: Path) -> list[Path]:
    exported: list[Path] = []
    for item in EXPORTS:
        source = repo_root / item.source
        target = repo_root / item.target
        if not source.exists():
            raise FileNotFoundError(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        exported.append(target)
    return exported


def stale_exports(repo_root: Path) -> list[Path]:
    """Committed copies that no longer match their rendered source."""
    stale: list[Path] = []
    for item in EXPORTS:
        source = repo_root / item.source
        target = repo_root / item.target
        if not source.exists():
            raise FileNotFoundError(source)
        if not target.exists() or not filecmp.cmp(source, target, shallow=False):
            stale.append(target)
    return stale


def main(argv: list[str]) -> int:
    """Parse first, act second.

    It took no arguments at all and ignored ``argv``, so ``--help`` silently re-exported the five
    SVGs — a script whose only documented interrogative does the thing instead of describing it.
    ``dump_openapi.py`` had the worse version of the same bug, writing the OpenAPI document to a file
    named ``--help``, and it grew an ``argparse`` for the same reason.

    ``--check`` came with the parser rather than after it: the five copies are committed artefacts
    derived from rendered diagrams, which is the drift class every other generated file here is gated
    on, and the tool that produces them is the only place that can say whether they are current.
    """
    parser = argparse.ArgumentParser(prog="export_doc_diagrams.py", description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report stale copies and exit non-zero, writing nothing"
    )
    args = parser.parse_args(argv[1:])

    repo_root = Path.cwd()
    if args.check:
        stale = stale_exports(repo_root)
        for target in stale:
            print(f"stale: {target.relative_to(repo_root)}", file=sys.stderr)
        if stale:
            print(
                "Run `uv run tools/docs/export_doc_diagrams.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        return 0
    for target in export_diagrams(repo_root):
        print(target.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
