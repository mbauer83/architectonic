"""Reads the one deployment-level, out-of-repo guidance-cache file into a domain
GuidanceOverlay (D2/D3a).

Guidance is a deployment concern, not a per-repository-tier one: one running instance of
this software pulls one guidance source, imported once via ``arch-import-guidance`` into a
local cache under the user's config directory, and integrated into the in-memory
meta-ontology representation at bootstrap. It is never split per engagement/enterprise repo
and never committed to either repo's git history.

Writing the cache file (the import CLI) is WU-B4; this module is the read side consumed at
bootstrap.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.domain.guidance.guidance import (
    GuidanceOverlay,
    WorkspaceGuidance,
    guidance_overlay_from_mapping,
    workspace_guidance_from_mapping,
)

_CONFIG_DIR = Path.home() / ".config" / "arch-repo"
GUIDANCE_CACHE_DIRNAME = "guidance-cache"


def guidance_cache_root() -> Path:
    return _CONFIG_DIR / GUIDANCE_CACHE_DIRNAME


def load_guidance_overlay(module_alias: str) -> GuidanceOverlay:
    """Read ``~/.config/arch-repo/guidance-cache/<module_alias>.guidance.yaml``.

    Returns an empty overlay when the file is absent — the default, license-safe state in
    which entities keep whatever ``create_when``/``never_create_when`` text the module ships
    inline (usually empty).
    """
    cache_file = guidance_cache_root() / f"{module_alias}.guidance.yaml"
    if not cache_file.is_file():
        return GuidanceOverlay()
    data = yaml.safe_load(cache_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return GuidanceOverlay()
    return guidance_overlay_from_mapping(data)


def load_workspace_guidance() -> WorkspaceGuidance:
    """Read ``~/.config/arch-repo/guidance-cache/workspace.guidance.yaml`` into a
    :class:`WorkspaceGuidance`.

    Returns an empty one when the file is absent — the default, license-safe state in which no
    workspace-scope guidance is served until a format-3 source is imported.
    """
    cache_file = guidance_cache_root() / "workspace.guidance.yaml"
    if not cache_file.is_file():
        return WorkspaceGuidance()
    data = yaml.safe_load(cache_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return WorkspaceGuidance()
    return workspace_guidance_from_mapping(data)
