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

from src.domain.deployment.layout import GUIDANCE_CACHE_DIRNAME  # noqa: F401 — re-exported for importers
from src.domain.guidance.guidance import (
    GuidanceOverlay,
    WorkspaceGuidance,
    guidance_overlay_from_mapping,
    workspace_guidance_from_mapping,
)
from src.domain.yaml_documents import parse_yaml


def guidance_cache_root() -> Path:
    """The cache this deployment reads and `arch-import-guidance` writes: the deployment manifest's.

    That is a deployment root's `guidance-cache/`, or `deployment.guidance_cache_root` in the settings
    document, or — when neither is set — `~/.config/arch-repo/guidance-cache`, which every installation
    of this user without its own shares. One resolution for the runtime, the import and the upgrade, so
    a deployment given its own cache is read from where `arch-repair upgrade` migrates it.
    """
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415 — the layout imports settings

    return resolve_manifest().guidance_cache_root.path


def load_guidance_overlay(module_alias: str) -> GuidanceOverlay:
    """Read ``<module_alias>.guidance.yaml`` in :func:`guidance_cache_root`.

    Returns an empty overlay when the file is absent — the default, license-safe state in
    which entities keep whatever ``create_when``/``never_create_when`` text the module ships
    inline (usually empty).
    """
    cache_file = guidance_cache_root() / f"{module_alias}.guidance.yaml"
    if not cache_file.is_file():
        return GuidanceOverlay()
    data = parse_yaml(cache_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return GuidanceOverlay()
    return guidance_overlay_from_mapping(data)


def load_workspace_guidance() -> WorkspaceGuidance:
    """Read ``workspace.guidance.yaml`` in :func:`guidance_cache_root` into a
    :class:`WorkspaceGuidance`.

    Returns an empty one when the file is absent — the default, license-safe state in which no
    workspace-scope guidance is served until a format-3 source is imported.
    """
    cache_file = guidance_cache_root() / "workspace.guidance.yaml"
    if not cache_file.is_file():
        return WorkspaceGuidance()
    data = parse_yaml(cache_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return WorkspaceGuidance()
    return workspace_guidance_from_mapping(data)
