"""Every committed diagram must render through the real PlantUML pipeline.

This is the regression guard for a class of false-positive verifications: a renderer
change is unit-tested in isolation and looks correct, but a stored diagram caches a
generated PUML body that has gone stale (or was authored by older renderer code), so the
*served* artifact fails to render even though the renderer's own tests pass.

It renders each diagram exactly as the serving endpoint does — `render_puml_svg(parsed
.puml_body, repo_root, diagram_type)` — and fails loudly on any PlantUML error, naming the
offending file. Confidential assurance diagrams (gated from on-disk rendering) are skipped.
Diagrams in group-collection subdirectories are included via a recursive scan, so a flat
layout is never assumed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2] / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"
_DIAGRAMS_DIR = _REPO_ROOT / "diagram-catalog" / "diagrams"


def _plantuml_available() -> bool:
    try:
        from src.application.verification.artifact_verifier_syntax import find_plantuml_jar
        return find_plantuml_jar() is not None
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _plantuml_available() or not _DIAGRAMS_DIR.is_dir(),
    reason="plantuml.jar or the self-model diagram catalog is unavailable",
)


def _committed_diagrams() -> list[Path]:
    # Recursive: group collections live in subdirectories of diagrams/.
    all_puml = sorted(_DIAGRAMS_DIR.rglob("*.puml"))
    # Honour the "committed" contract literally: only git-tracked diagrams. The renderer
    # writes a `tmp*.puml` into this catalog so `!include`s resolve, then removes it in a
    # `finally`; if a render process is hard-killed (SIGKILL) mid-run that cleanup is
    # skipped, orphaning a frontmatter-less temp file here. Rendering that stray would fail
    # with a spurious unknown-diagram-type error, so untracked files are excluded.
    try:
        listed = subprocess.run(
            ["git", "-C", str(_DIAGRAMS_DIR), "ls-files", "-z", "--", "."],
            capture_output=True,
            timeout=30,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError):
        return all_puml
    tracked = {(_DIAGRAMS_DIR / rel).resolve() for rel in listed.split("\0") if rel.endswith(".puml")}
    if not tracked:
        # A workspace whose repository is not committed yet tracks NOTHING — the git
        # filter would silently empty this suite (and it did: the GraphViz-crash class
        # went unguarded). The filter exists only to drop the renderer's orphaned
        # `tmp*.puml` strays, so with no tracked files fall back to exactly that.
        return [p for p in all_puml if not p.name.startswith("tmp")]
    return [p for p in all_puml if p.resolve() in tracked]


@pytest.mark.parametrize("diagram_path", _committed_diagrams(), ids=lambda p: p.stem)
def test_committed_diagram_renders(diagram_path: Path) -> None:
    from src.infrastructure.rendering.diagram_builder import render_puml_svg
    from src.infrastructure.write.artifact_write.diagram_confidentiality import is_confidential_diagram_source
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    parsed = parse_diagram_file(diagram_path)
    diagram_type = str(parsed.frontmatter.get("diagram-type", "archimate"))
    tlp = parsed.frontmatter.get("tlp")
    if is_confidential_diagram_source(diagram_type, tlp if isinstance(tlp, str) else None):
        pytest.skip("confidential assurance diagram — gated from on-disk rendering")

    svg, warnings = render_puml_svg(parsed.puml_body, _REPO_ROOT, diagram_type)
    assert svg is not None, f"{diagram_path.name} failed to render: {'; '.join(warnings)}"
    assert svg.lstrip().startswith("<svg") or "<svg" in svg[:200], (
        f"{diagram_path.name} produced non-SVG output"
    )
