"""Shared ID-generation helpers for assurance store adapters."""

from __future__ import annotations

import hashlib
import random
import string
import time

from src.domain.assurance.assurance_node_types import NODE_ID_PREFIXES
from src.domain.clock import epoch_seconds


def make_node_id(node_type: str, name: str) -> str:
    """An id for a new node, prefixed as its type declares.

    An unknown type raises rather than falling back to a prefix derived from its name. The fallback
    this replaces is how two types came to carry a prefix nothing declared: it produced a plausible
    id, the write succeeded, and the mistake was persisted with no signal anywhere.
    """
    prefix = NODE_ID_PREFIXES.get(node_type)
    if prefix is None:
        raise ValueError(
            f"No id prefix is declared for assurance node type {node_type!r}. Add it to "
            "NODE_ID_PREFIXES alongside the ontology's declaration rather than letting an "
            "undeclared type be persisted under an invented prefix."
        )
    epoch = epoch_seconds()
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    slug = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{prefix}@{epoch}.{rand}.{slug}"


def make_edge_id(source_id: str, target_id: str, conn_type: str) -> str:
    raw = f"{source_id}--{target_id}--{conn_type}--{time.time()}"
    return "EDG@" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def make_analysis_id(method: str, name: str) -> str:
    """Generate a stable-prefixed id for an assurance analysis aggregate.

    Prefix is the analysis method (STPA/CAST/GRC); an epoch + random suffix
    avoids collisions, mirroring make_node_id.
    """
    prefix = method[:4].upper() if method else "ANL"
    epoch = epoch_seconds()
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    slug = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{prefix}@{epoch}.{rand}.{slug}"


def make_group_id(name: str) -> str:
    """Stable-prefixed id for an assurance group.

    `GRP` rather than a method prefix: a group is filing and has no method, which is exactly
    what distinguishes it from the analyses it holds.
    """
    epoch = epoch_seconds()
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    slug = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"GRP@{epoch}.{rand}.{slug}"
