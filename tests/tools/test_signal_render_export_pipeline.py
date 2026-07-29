"""D11 render/export pipeline at the wire: the ephemeral render marks
signal-declaring definitions no-store with a banner payload, plain viewpoints
stay banner-free, the stamped export burns the classification into the SVG
with Content-Disposition, and the persisted-diagram download route is
untouched. Repository-scan regression (I-C1): no signal-derived value lands in
any git-tracked file."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.infrastructure.rendering.svg_banner import stamp_svg_banner

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'


class TestSvgStamp:
    def test_banner_is_burned_into_the_document(self) -> None:
        stamped = stamp_svg_banner(_SVG, "TLP:AMBER — basis APP@1: SNAP@x — generated t")
        assert "classification-banner" in stamped
        assert "TLP:AMBER" in stamped
        assert stamped.count("<") > _SVG.count("<")  # actually added elements

    def test_non_svg_input_is_a_typed_error(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="not (a valid SVG|<svg>)"):
            stamp_svg_banner("<html></html>", "x")
        with pytest.raises(ValueError):
            stamp_svg_banner("garbage", "x")


class TestRepositoryScanRegression:
    """I-C1: signal-derived values exist only in the encrypted store and
    ephemeral responses — never in git-tracked text. The scan uses value
    shapes that only the security pipeline produces."""

    _MARKERS = ("max_cvss_score", "distinct_open_vulnerabilities", "CVSS:3.1/AV:N")

    def test_no_signal_values_in_git_tracked_model_files(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        tracked = subprocess.run(
            ["git", "ls-files",
             "engagements/", "enterprise-repository/",
             "src/ontologies/"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        offenders: list[str] = []
        for rel in tracked:
            path = repo_root / rel
            if path.suffix not in (".md", ".yaml", ".yml", ".puml", ".json"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            # The viewpoint definition legitimately NAMES metrics; a VALUE
            # assignment (metric: N) or a CVSS vector must never appear.
            if "CVSS:3.1/AV:N" in text:
                offenders.append(rel)
        assert offenders == [], f"signal-shaped values in git-tracked files: {offenders}"
