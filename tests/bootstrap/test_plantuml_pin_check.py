"""`get-plantuml --check` says whether the jar on disk is the release this source pins.

It printed a digest and left the comparison to the reader. The updater needs the answer, because a
release may move `PLANTUML_VERSION` and a jar left from the previous pin renders with the previous
PlantUML; so the command answers it, against Maven Central's sidecar for the pinned version, and an
unreachable sidecar is "unverifiable", never "wrong".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.infrastructure.bootstrap import get_plantuml

_JAR = b"the pinned jar"
_DIGEST = hashlib.sha256(_JAR).hexdigest()


def _sidecar(monkeypatch: pytest.MonkeyPatch, body: bytes | None) -> None:
    def download_bytes(url: str, *, label: str | None = None) -> bytes:
        assert url.endswith(f"plantuml-{get_plantuml.PLANTUML_VERSION}.jar.sha256")
        if body is None:
            raise SystemExit(f"Download error: {url}")
        return body

    monkeypatch.setattr(get_plantuml, "download_bytes", download_bytes)


def test_the_pinned_jar_is_recognised(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(_JAR)
    _sidecar(monkeypatch, f"{_DIGEST.upper()}  plantuml.jar\n".encode())

    assert get_plantuml.installed_jar_matches_pin(jar) is True
    assert get_plantuml.check(jar) == 0
    assert "pinned" in capsys.readouterr().out


def test_another_jar_is_reported_and_fails_the_check(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"an older release")
    _sidecar(monkeypatch, f"{_DIGEST}\n".encode())

    assert get_plantuml.installed_jar_matches_pin(jar) is False
    assert get_plantuml.check(jar) == 1
    assert "NO" in capsys.readouterr().out


def test_an_unreachable_sidecar_is_unverifiable_not_wrong(monkeypatch, tmp_path: Path, capsys) -> None:  # noqa: ANN001
    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(_JAR)
    _sidecar(monkeypatch, None)

    assert get_plantuml.installed_jar_matches_pin(jar) is None
    assert get_plantuml.check(jar) == 0
    assert "unverifiable" in capsys.readouterr().out


def test_no_jar_is_no_answer(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _sidecar(monkeypatch, f"{_DIGEST}\n".encode())
    assert get_plantuml.installed_jar_matches_pin(tmp_path / "missing.jar") is None
