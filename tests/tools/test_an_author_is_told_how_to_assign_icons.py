"""Authoring guidance for a diagram type says how to give its elements icons, in the styles it draws."""

from __future__ import annotations

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp


@pytest.mark.parametrize(
    ("diagram_type", "styles"),
    [("archimate-technology", ["badge", "figure"]), ("c4-container", ["badge"]), ("gsn", None)],
)
def test_the_guidance_names_the_styles_the_type_draws(diagram_type: str, styles: list[str] | None) -> None:
    block = mcp.artifact_authoring_guidance(diagram_type=diagram_type)["diagram_type_guidance"]

    icons = block.get("icons")
    assert (icons or {}).get("styles") == styles
    if icons:
        assert {"display_icons", "type_icons", "icons"} <= set(icons["statements"])
        assert "artifact_query_icons" in icons["find"]
