"""Reading an MCP tool's answer: the transport envelope, then the payload.

Shared by the read walk and the write walk, because both are asking the same question of the same
surface and a second decoder would be a second thing to get wrong. It was one function in
`conformance.py` until the write half needed it; extracting it is the alternative to importing the
read walk from the write walk for two helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def text_of(result: Any) -> str:
    """The tool's answer as text. MCP wraps content in a list of typed blocks."""
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def decoded(text: str) -> object:
    """The answer as data. **YAML**, which is what this surface serves.

    verifies: REQ@1776705655.Ga1zwy  (YAML instead of JSON for structured output via MCP)
    verifies: REQ@1712870400.peinbQ  (MCP is one of the three tool interfaces, walked over its transport)

    The first version of this walk asserted JSON and reported every tool as broken. That is the
    harness being wrong about the contract rather than the contract being wrong — `_dump_yaml_text`
    in `name_normalization` is deliberate, and an agent reading a tool result reads YAML. Worth
    recording, because "the answer is not JSON" is exactly the sort of confident false positive that
    makes a new gate get switched off.
    """
    import yaml

    return yaml.safe_load(text)


def rows_of(payload: object) -> list[Mapping[str, Any]]:
    """The list a catalogue read answers with, wherever it put it.

    Some tools wrap their payload in ``result``; others answer a mapping directly. Both are read
    rather than assumed, so a seed does not silently come back empty because the envelope moved.
    """
    if isinstance(payload, Mapping):
        for key in ("result", "artifacts", "items", "nodes", "results"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, Mapping)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    return []


def refusal(payload: object) -> str | None:
    """The reason this answer is a refusal, or ``None`` if it is not one.

    **This is the whole point of the write walk.** A refused write arrives inside a *success*: the
    tool answers normally with ``wrote: false`` and the reason under ``verification.issues``, or
    ``ok: false`` with an ``error``. A caller that checked only for a raised exception — which is
    what the read walk checks, because a read has no such flag — reads a refusal as coverage. Both
    shapes are read because the write mount serves both: the artifact tools report ``wrote``, the
    viewpoint and sync tools report ``ok``.

    Absence of any of them is not a refusal. Several tools on these mounts are reads in write clothing
    (`artifact_help`, `artifact_get_operation`) and answer none.

    **Three shapes, because the two mounts refuse differently.** The artifact tools report ``wrote``, the
    viewpoint and sync tools report ``ok``, and the *assurance* tools report neither: a locked store, an
    absent node or a rejected field comes back as a bare ``{"error": …, "message": …}``. Walking the
    assurance mount with only the first two recognised meant its refusals read as coverage — which is
    the exact failure this function is named after, and it was introduced by the commit that started
    walking that mount. Found by the REST walk answering 409 for a write the MCP walk had reported green.
    """
    if not isinstance(payload, Mapping):
        return None
    if payload.get("wrote") is False:
        verification = payload.get("verification")
        issues = (verification or {}).get("issues") if isinstance(verification, Mapping) else None
        return f"wrote: false — {issues or payload.get('error') or payload}"
    if payload.get("ok") is False:
        return f"ok: false — {payload.get('error') or payload}"
    error = payload.get("error")
    if isinstance(error, str) and error:
        return f"error: {error} — {payload.get('message') or payload}"
    return None
