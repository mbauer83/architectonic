"""Tests for check_diagram_runtime.py pure functions.

Covers _parse_version (regex matching, None on no match), the jar resolution the
checker shares with the renderer, and main() early-exit paths that don't require
subprocesses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.bootstrap import check_diagram_runtime
from src.infrastructure.bootstrap.check_diagram_runtime import _parse_version, main


class TestParseVersion:
    def test_parses_standard_version(self) -> None:
        result = _parse_version("version 2.50.0")
        assert result == (2, 50, 0)

    def test_parses_from_longer_string(self) -> None:
        result = _parse_version("Graphviz - Graph Visualization Software\ndot - graphviz version 8.1.0")
        assert result == (8, 1, 0)

    def test_parses_major_only_style(self) -> None:
        result = _parse_version("plantuml 1.2.3 (GPL)")
        assert result == (1, 2, 3)

    def test_returns_none_when_no_version(self) -> None:
        result = _parse_version("no version here")
        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        result = _parse_version("")
        assert result is None

    def test_returns_none_for_partial_version(self) -> None:
        result = _parse_version("version 1.2")
        assert result is None


class TestMainEarlyExits:
    def test_missing_jar_raises_system_exit(self, tmp_path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--jar", str(tmp_path / "nonexistent.jar")])
        assert "not found" in str(exc_info.value)

    def test_invalid_min_graphviz_raises_system_exit(self, tmp_path) -> None:
        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"fake")
        with pytest.raises(SystemExit) as exc_info:
            main(["--jar", str(jar), "--min-graphviz", "not-a-version"])
        assert "min-graphviz" in str(exc_info.value).lower()


class TestJarResolution:
    """Without --jar the checker looks exactly where the renderer looks.

    A check that names its own path can report "plantuml.jar not found" for a jar every
    renderer in the process resolves — the documented ``get-plantuml &&
    check-diagram-runtime`` pair has to agree on the location to mean anything.
    """

    def test_delegates_to_the_renderers_lookup_when_no_jar_is_given(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"fake")
        monkeypatch.setattr(check_diagram_runtime, "find_plantuml_jar", lambda: jar)

        # Past the jar check; --min-graphviz is what stops it, proving the jar resolved.
        with pytest.raises(SystemExit) as exc_info:
            main(["--min-graphviz", "not-a-version"])
        assert "min-graphviz" in str(exc_info.value).lower()

    def test_reports_an_actionable_message_when_no_jar_exists_anywhere(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(check_diagram_runtime, "find_plantuml_jar", lambda: None)
        with pytest.raises(SystemExit) as exc_info:
            main([])
        message = str(exc_info.value)
        assert "not found" in message
        assert "get-plantuml" in message

    def test_explicit_jar_still_wins_over_the_lookup(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(check_diagram_runtime, "find_plantuml_jar", lambda: tmp_path / "found.jar")
        with pytest.raises(SystemExit) as exc_info:
            main(["--jar", str(tmp_path / "explicit.jar")])
        assert "explicit.jar" in str(exc_info.value)


def test_get_plantuml_writes_where_the_lookup_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two CLIs the quickstart chains agree on a location.

    ``get-plantuml``'s default output has to be one of the relative paths
    ``find_plantuml_jar()`` walks up to pyproject.toml looking for; anywhere else and a
    successful download is invisible to both the checker and the renderer.
    """
    from src.application.verification.artifact_verifier_syntax import PLANTUML_JAR_RELPATHS
    from src.infrastructure.bootstrap import get_plantuml

    written: list[Path] = []

    def _capture(version: str, output: Path, *, force: bool) -> int:
        written.append(output)
        return 0

    monkeypatch.setattr(get_plantuml, "download", _capture)
    with pytest.raises(SystemExit) as exc_info:
        get_plantuml.main([])
    assert exc_info.value.code == 0

    assert [path.as_posix() for path in written] == [PLANTUML_JAR_RELPATHS[0]]
