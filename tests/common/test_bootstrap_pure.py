"""Tests for pure-logic functions in bootstrap modules.

Covers: version parsing, SHA-256 hashing, platform install plan lookup,
check() and download() short-circuit paths (no network/subprocess calls).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# get_diagram_runtime: pure helpers
# ---------------------------------------------------------------------------


class TestParseVersionGetDiagramRuntime:
    def test_parses_standard_version(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _parse_version

        assert _parse_version("dot - graphviz version 14.1.5 (20250327.1745)") == (14, 1, 5)

    def test_parses_version_at_start(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _parse_version

        assert _parse_version("2.49.0") == (2, 49, 0)

    def test_returns_none_when_no_version(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _parse_version

        assert _parse_version("no version here") is None

    def test_returns_none_for_empty_string(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _parse_version

        assert _parse_version("") is None


class TestSha256HexGetDiagramRuntime:
    def test_returns_hex_string(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _sha256hex

        result = _sha256hex(b"hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _sha256hex

        assert _sha256hex(b"test") == _sha256hex(b"test")

    def test_different_inputs_differ(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _sha256hex

        assert _sha256hex(b"a") != _sha256hex(b"b")


class TestGraphvizInstallPlans:
    def test_darwin_has_brew(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _GRAPHVIZ_INSTALL_PLANS

        darwin_plans = _GRAPHVIZ_INSTALL_PLANS.get("darwin", [])
        tools = [tool for tool, _ in darwin_plans]
        assert "brew" in tools

    def test_linux_has_apt_get(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _GRAPHVIZ_INSTALL_PLANS

        linux_plans = _GRAPHVIZ_INSTALL_PLANS.get("linux", [])
        tools = [tool for tool, _ in linux_plans]
        assert "apt-get" in tools

    def test_windows_has_winget_or_choco(self) -> None:
        from src.infrastructure.bootstrap.get_diagram_runtime import _GRAPHVIZ_INSTALL_PLANS

        win_plans = _GRAPHVIZ_INSTALL_PLANS.get("windows", [])
        tools = [tool for tool, _ in win_plans]
        assert "winget" in tools or "choco" in tools


# ---------------------------------------------------------------------------
# check_diagram_runtime: _parse_version
# ---------------------------------------------------------------------------


class TestParseVersionCheckDiagramRuntime:
    def test_parses_standard_version(self) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import _parse_version

        assert _parse_version("1.2026.3") == (1, 2026, 3)

    def test_parses_version_from_verbose_string(self) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import _parse_version

        assert _parse_version("PlantUML version 1.2026.3 (2026-02-01)") == (1, 2026, 3)

    def test_returns_none_for_no_match(self) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import _parse_version

        assert _parse_version("no version") is None

    def test_returns_none_for_empty(self) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import _parse_version

        assert _parse_version("") is None


class TestCheckDiagramRuntimeMain:
    def test_main_raises_when_jar_missing(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import main

        jar = str(tmp_path / "nonexistent.jar")
        with pytest.raises(SystemExit, match="not found"):
            main(["--jar", jar])

    def test_main_raises_when_bad_min_version(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.check_diagram_runtime import main

        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"fake jar")
        with pytest.raises(SystemExit, match="parse"):
            main(["--jar", str(jar), "--min-graphviz", "notaversion"])


# ---------------------------------------------------------------------------
# get_plantuml: pure helpers
# ---------------------------------------------------------------------------


class TestSha256HexGetPlantuml:
    def test_returns_hex_string(self) -> None:
        from src.infrastructure.bootstrap.get_plantuml import _sha256hex

        result = _sha256hex(b"test data")
        assert len(result) == 64

    def test_known_value(self) -> None:
        import hashlib

        from src.infrastructure.bootstrap.get_plantuml import _sha256hex

        expected = hashlib.sha256(b"").hexdigest()
        assert _sha256hex(b"") == expected


class TestGetPlantumlCheck:
    def test_check_returns_1_when_file_missing(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.get_plantuml import check

        result = check(tmp_path / "nonexistent.jar")
        assert result == 1

    def test_check_returns_0_when_file_exists(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.get_plantuml import check

        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"fake jar content")
        result = check(jar)
        assert result == 0


class TestGetPlantumlDownload:
    def test_download_returns_0_when_file_exists_no_force(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.get_plantuml import download

        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"existing jar")
        result = download("1.2026.3", jar, force=False)
        assert result == 0
        # File should not be overwritten
        assert jar.read_bytes() == b"existing jar"


class TestGetPlantumlMain:
    def test_main_check_returns_1_when_file_missing(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.get_plantuml import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--check", "--output", str(tmp_path / "nonexistent.jar")])
        assert exc_info.value.code == 1

    def test_main_check_returns_0_when_file_exists(self, tmp_path: Path) -> None:
        from src.infrastructure.bootstrap.get_plantuml import main

        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"fake")
        with pytest.raises(SystemExit) as exc_info:
            main(["--check", "--output", str(jar)])
        assert exc_info.value.code == 0
