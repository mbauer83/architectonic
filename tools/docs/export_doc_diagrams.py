#!/usr/bin/env python3
"""Export rendered self-model diagrams used by the public docs."""

from __future__ import annotations

import shutil
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


def main() -> int:
    repo_root = Path.cwd()
    for target in export_diagrams(repo_root):
        print(target.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
