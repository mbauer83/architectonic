"""Unit tests for resolve_java_executable() — the user-settable JRE resolver.

Precedence (highest first): ARCH_JAVA env > JAVA_HOME > "java" on PATH. The
override is consulted only when explicitly set, so the bundled OpenJDK default is
never silently replaced by an incompatible one. This mirrors the GRAPHVIZ_DOT
escape hatch for the sibling diagram-runtime binary — an environment channel,
keeping the application layer free of a configuration-module dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification import artifact_verifier_syntax as mod

_ENV_KEYS = ("ARCH_JAVA", "JAVA_HOME")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestResolveJavaExecutable:
    def test_default_is_bare_java(self, clean_env: None) -> None:
        assert mod.resolve_java_executable() == "java"

    def test_java_home_used_when_set(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JAVA_HOME", "/usr/lib/jvm/openjdk-17")
        assert mod.resolve_java_executable() == str(Path("/usr/lib/jvm/openjdk-17") / "bin" / "java")

    def test_arch_java_env_overrides_java_home(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JAVA_HOME", "/usr/lib/jvm/openjdk-17")
        monkeypatch.setenv("ARCH_JAVA", "/explicit/jre/bin/java")
        assert mod.resolve_java_executable() == "/explicit/jre/bin/java"

    def test_arch_java_is_tilde_expanded(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARCH_JAVA", "~/jdk/bin/java")
        resolved = mod.resolve_java_executable()
        assert "~" not in resolved
        assert resolved.endswith("/jdk/bin/java")

    def test_blank_arch_java_falls_through_to_default(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARCH_JAVA", "   ")
        assert mod.resolve_java_executable() == "java"

    def test_blank_java_home_falls_through_to_default(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JAVA_HOME", "  ")
        assert mod.resolve_java_executable() == "java"
