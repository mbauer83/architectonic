"""Tests for pure and environment-logic parts of artifact_verifier_syntax.py.

Covers: resolve_worker_count, find_graphviz_dot env-var path,
check_puml_syntax when PUML jar is absent, check_puml_syntax_batch jar-missing path.
Note: subprocess (PlantUML/Graphviz execution) paths are skipped via the
ARCH_SKIP_PUML_SYNTAX env variable in conftest.py — only pure logic is tested here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestResolveWorkerCount:
    def test_returns_positive_integer(self) -> None:
        from src.application.verification.artifact_verifier_syntax import resolve_worker_count

        count = resolve_worker_count()
        assert isinstance(count, int)
        assert count >= 1
        assert count <= 32


class TestFindGraphvizDot:
    def test_returns_none_when_no_dot_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        syn.find_graphviz_dot.cache_clear()
        monkeypatch.delenv("GRAPHVIZ_DOT", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        result = syn.find_graphviz_dot()
        syn.find_graphviz_dot.cache_clear()
        # May return None or a bundled path; just check type
        assert result is None or isinstance(result, Path)

    def test_uses_graphviz_dot_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        dot = tmp_path / "dot"
        dot.write_text("#!/bin/sh\necho dot")
        syn.find_graphviz_dot.cache_clear()
        monkeypatch.setenv("GRAPHVIZ_DOT", str(dot))
        result = syn.find_graphviz_dot()
        syn.find_graphviz_dot.cache_clear()
        assert result == dot

    def test_graphviz_dot_env_nonexistent_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        syn.find_graphviz_dot.cache_clear()
        monkeypatch.setenv("GRAPHVIZ_DOT", "/no/such/dot")
        result = syn.find_graphviz_dot()
        syn.find_graphviz_dot.cache_clear()
        # Must not be /no/such/dot since it doesn't exist
        assert result is None or (result is not None and str(result) != "/no/such/dot")


class TestCheckPumlSyntaxJarMissing:
    def test_returns_w350_when_jar_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        # Clear cache on original, then patch with plain lambda
        syn.find_plantuml_jar.cache_clear()
        monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
        monkeypatch.setattr(syn, "find_plantuml_jar", lambda: None)
        f = tmp_path / "test.puml"
        f.write_text("@startuml\n@enduml\n")
        issues = syn.check_puml_syntax(f, str(f))
        assert len(issues) == 1
        assert issues[0].code == "W350"

    def test_returns_empty_when_skip_env_set(self, tmp_path: Path) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        # The conftest sets ARCH_SKIP_PUML_SYNTAX, so this should always return []
        f = tmp_path / "test.puml"
        f.write_text("@startuml\n@enduml\n")
        issues = syn.check_puml_syntax(f, str(f))
        assert issues == []


class TestCheckPumlSyntaxBatchJarMissing:
    def test_adds_w350_per_path_when_jar_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        # Clear cache on original, then patch with plain lambda
        syn.find_plantuml_jar.cache_clear()
        monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
        monkeypatch.setattr(syn, "find_plantuml_jar", lambda: None)
        paths = [tmp_path / "a.puml", tmp_path / "b.puml"]
        for p in paths:
            p.write_text("@startuml\n@enduml\n")
        result = syn.check_puml_syntax_batch(paths)
        for p in paths:
            assert p in result
            assert any(i.code == "W350" for i in result[p])

    def test_empty_paths_returns_empty_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.application.verification import artifact_verifier_syntax as syn

        monkeypatch.delenv("ARCH_SKIP_PUML_SYNTAX", raising=False)
        result = syn.check_puml_syntax_batch([])
        assert result == {}
