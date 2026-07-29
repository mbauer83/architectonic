"""The on-demand SVG endpoint gates confidential assurance diagrams behind the unlocked store.

This is the #14 assurance-context viewer: confidential assurance diagrams have no on-disk
image (G-f), so they are rendered on demand in memory — but only when the confidential store
is unlocked. A locked store yields HTTP 403, not a silent leak.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from src.infrastructure.gui.routers import _diagram_serving as serving


def _write_confidential_bowtie(tmp_path: Path) -> Path:
    p = tmp_path / "BOWTIE@1.aaaaaa.x.puml"
    p.write_text(
        "---\nartifact-id: BOWTIE@1.aaaaaa.x\nartifact-type: diagram\nname: X\n"
        "diagram-type: bowtie\ntlp: TLP:AMBER\nversion: 0.1.0\nstatus: draft\n"
        "last-updated: '2026-06-16'\n---\n@startuml\n@enduml\n",
        encoding="utf-8",
    )
    return p


def test_confidential_helper_reads_tlp(tmp_path: Path) -> None:
    p = _write_confidential_bowtie(tmp_path)
    assert serving._is_confidential_diagram(p, "bowtie") is True


def test_publishable_assurance_diagram_is_not_gated(tmp_path: Path) -> None:
    p = tmp_path / "BOWTIE@1.bbbbbb.y.puml"
    p.write_text(
        "---\nartifact-id: BOWTIE@1.bbbbbb.y\nartifact-type: diagram\nname: Y\n"
        "diagram-type: bowtie\ntlp: TLP:GREEN\nversion: 0.1.0\nstatus: draft\n"
        "last-updated: '2026-06-16'\n---\n@startuml\n@enduml\n",
        encoding="utf-8",
    )
    assert serving._is_confidential_diagram(p, "bowtie") is False


def test_locked_store_yields_403_for_confidential_diagram(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_confidential_bowtie(tmp_path)

    class _Diag:
        diagram_type = "bowtie"
        path = p

    class _Repo:
        def get_diagram(self, _id: str) -> object:
            return _Diag()

    monkeypatch.setattr(serving.s, "maybe_engagement_root", lambda: tmp_path)
    monkeypatch.setattr(serving.s, "get_repo", lambda: _Repo())

    # Locked store: the assurance context reports unavailable -> 403, never rendering plaintext.
    import src.infrastructure.mcp.assurance_mcp.context as ctx

    class _Unavailable:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(ctx, "get_assurance_context", lambda: _Unavailable())

    with pytest.raises(HTTPException) as exc_info:
        serving.get_diagram_svg("BOWTIE@1.aaaaaa.x")
    assert exc_info.value.status_code == 403
