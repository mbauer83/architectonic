"""Public facade for deterministic artifact-writing helpers.

This module is the stable import surface used by the write layer. It exposes:
- ontology-backed entity/connection catalogs
- ID generation helpers
- deterministic formatting helpers for entity, connection, diagram, and matrix artifacts
- best-effort inference of referenced IDs from PUML

I/O (writing files, cache invalidation, verifier execution)
belongs in infrastructure adapters (see ``src/infrastructure/write/artifact_write_ops.py``).
"""

import re
import secrets
import string
from collections.abc import Mapping

from src.application.modeling.artifact_write_formatting import (
    format_diagram_puml,
    format_entity_markdown,
    format_matrix_markdown,
    format_outgoing_markdown,
)
from src.application.modeling.types import (
    DiagramConnectionInferenceMode,
)
from src.domain.clock import epoch_seconds

__all__ = [
    "DiagramConnectionInferenceMode",
    "format_diagram_puml",
    "format_entity_markdown",
    "format_matrix_markdown",
    "format_outgoing_markdown",
    "generate_diagram_id",
    "generate_entity_id",
    "infer_archimate_connection_ids_from_puml",
    "infer_entity_ids_from_puml",
    "prefix_for_diagram_type",
    "slugify",
]

# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

_ID_ALPHABET = string.ascii_letters + string.digits + "-_"


def slugify(value: str) -> str:
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "entity"


def generate_entity_id(prefix: str, friendly_name: str, *, random_length: int = 6) -> str:
    """Generate an artifact-id in the new convention: TYPE@epoch.random.friendly-name"""
    epoch = epoch_seconds()
    random_part = "".join(secrets.choice(_ID_ALPHABET) for _ in range(random_length))
    slug = slugify(friendly_name)
    return f"{prefix}@{epoch}.{random_part}.{slug}"


_DIAGRAM_TYPE_PREFIXES: dict[str, str] = {
    "matrix": "MAT",
    "sequence": "SEQ",
    "er": "ERD",
    "erd": "ERD",
    "entity-relationship": "ERD",
    "activity": "ACT",
    "bpmn": "BPMN",
}


def prefix_for_diagram_type(diagram_type: str) -> str:
    """Return a stable artifact-id prefix for a diagram type."""
    normalized = diagram_type.strip().lower()
    if normalized.startswith("archimate"):
        return "ARC"
    if normalized in _DIAGRAM_TYPE_PREFIXES:
        return _DIAGRAM_TYPE_PREFIXES[normalized]

    parts = [part for part in re.split(r"[^a-z0-9]+", normalized) if part]
    if not parts:
        return "DGM"

    letters = "".join(part[0] for part in parts[:6]).upper()
    if len(letters) >= 2:
        return letters[:6]

    compact = "".join(parts).upper()
    if len(compact) >= 2:
        return compact[:6]

    return "DGM"


def generate_diagram_id(diagram_type: str, friendly_name: str, *, random_length: int = 6) -> str:
    """Generate a typed diagram artifact-id from diagram_type + friendly name."""
    return generate_entity_id(
        prefix_for_diagram_type(diagram_type),
        friendly_name,
        random_length=random_length,
    )


# ---------------------------------------------------------------------------
# PUML inference
# ---------------------------------------------------------------------------


def infer_entity_ids_from_puml(puml: str) -> tuple[set[str], list[str]]:
    """Infer entity IDs from PUML.

    Returns (ids, warnings). Looks for alias tokens like ``DRV_Qw7Er1`` and
    maps them back to entity IDs by searching for the full artifact-id containing
    the random part.
    """
    warnings: list[str] = []
    ids: set[str] = set()

    # Match aliases: TYPE_random (e.g. DRV_Qw7Er1, APP_kRZYOA)
    for m in re.finditer(r"\b([A-Z]{2,6})_([A-Za-z0-9_-]{4,})\b", puml):
        alias = f"{m.group(1)}_{m.group(2)}"
        ids.add(alias)

    if not ids:
        warnings.append(
            "No entity aliases found in PUML. For best discoverability, use standard aliases like DRV_Qw7Er1."
        )

    return ids, warnings


def infer_archimate_connection_ids_from_puml(
    puml: str,
    *,
    mode: DiagramConnectionInferenceMode,
    stereotype_map: Mapping[str, str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Infer ArchiMate connections from PUML lines with <<relationship>> stereotypes.

    Returns (connections, warnings) where each connection is a dict with
    ``source_alias``, ``target_alias``, and ``connection_type``.
    """
    warnings: list[str] = []
    connections: list[dict[str, str]] = []

    # Pattern matches e.g. DRV_Qw7Er1 -[#color]-> GOL_Po1Qw3 : <<realization>>
    pat = re.compile(
        r"\b(?P<src>[A-Z]{2,6}_[A-Za-z0-9_-]+)\b.*?\b(?P<tgt>[A-Z]{2,6}_[A-Za-z0-9_-]+)\b\s*:\s*<<(?P<rel>[A-Za-z]+)>>",
        flags=re.IGNORECASE,
    )

    for m in pat.finditer(puml):
        src = m.group("src")
        tgt = m.group("tgt")
        rel = m.group("rel").strip().lower()
        conn_type = stereotype_map.get(rel)
        if conn_type is None:
            msg = f"Unknown ArchiMate relationship stereotype <<{m.group('rel')}>>"
            if mode == "strict":
                raise ValueError(msg)
            warnings.append(msg)
            continue

        connections.append(
            {
                "source_alias": src,
                "target_alias": tgt,
                "connection_type": conn_type,
            }
        )

    return connections, warnings
