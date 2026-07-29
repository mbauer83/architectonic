"""PocketBase sidecar lifecycle helpers for the confidential assurance store.

Provides collection-schema initialisation via the PocketBase admin API.
The user is responsible for downloading and starting the PocketBase binary;
this module handles the collection schema setup and health checks via REST.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Minimal field definitions for each collection.
_ANALYSES_FIELDS = [
    {"name": "analysis_id", "type": "text", "required": True},
    {"name": "group_id", "type": "text", "required": False},
    {"name": "name", "type": "text", "required": True},
    {"name": "method", "type": "text", "required": True},
    {"name": "architecture_anchor_id", "type": "text", "required": False},
    {"name": "status", "type": "text", "required": False},
    {"name": "tlp", "type": "text", "required": False},
    {"name": "created_at", "type": "text", "required": False},
    {"name": "updated_at", "type": "text", "required": False},
]

_NODES_FIELDS = [
    {"name": "node_id", "type": "text", "required": True},
    {"name": "node_type", "type": "text", "required": True},
    {"name": "name", "type": "text", "required": True},
    {"name": "status", "type": "text", "required": False},
    {"name": "tlp", "type": "text", "required": False},
    {"name": "concern_class", "type": "text", "required": False},
    {"name": "disposition", "type": "text", "required": False},
    {"name": "failure_type", "type": "text", "required": False},
    {"name": "mode", "type": "text", "required": False},
    {"name": "uca_type", "type": "text", "required": False},
    {"name": "binding_status", "type": "text", "required": False},
    {"name": "node_role", "type": "text", "required": False},
    {"name": "analysis_id", "type": "text", "required": False},
    {"name": "attributes_json", "type": "text", "required": False},
    {"name": "content_text", "type": "text", "required": False},
    {"name": "created_at", "type": "text", "required": False},
    {"name": "updated_at", "type": "text", "required": False},
]

_EDGES_FIELDS = [
    {"name": "edge_id", "type": "text", "required": True},
    {"name": "source_id", "type": "text", "required": True},
    {"name": "target_id", "type": "text", "required": True},
    {"name": "conn_type", "type": "text", "required": True},
    {"name": "attributes_json", "type": "text", "required": False},
    {"name": "created_at", "type": "text", "required": False},
]

_REFS_FIELDS = [
    {"name": "assurance_node_id", "type": "text", "required": True},
    {"name": "arch_artifact_id", "type": "text", "required": True},
    {"name": "ref_type", "type": "text", "required": True},
    {"name": "resolved_at", "type": "text", "required": False},
]

_GROUPS_FIELDS = [
    {"name": "group_id", "type": "text", "required": True},
    {"name": "name", "type": "text", "required": True},
    {"name": "description", "type": "text", "required": False},
    {"name": "created_at", "type": "text", "required": False},
    {"name": "updated_at", "type": "text", "required": False},
]

_MEMBERS_FIELDS = [
    {"name": "analysis_id", "type": "text", "required": True},
    {"name": "node_id", "type": "text", "required": True},
    {"name": "added_at", "type": "text", "required": False},
]

_COLLECTIONS = [
    ("assurance_groups", _GROUPS_FIELDS),
    ("assurance_analyses", _ANALYSES_FIELDS),
    ("assurance_nodes", _NODES_FIELDS),
    ("assurance_edges", _EDGES_FIELDS),
    ("arch_refs", _REFS_FIELDS),
    ("assurance_analysis_members", _MEMBERS_FIELDS),
]


def check_health(base_url: str) -> bool:
    """Return True if the PocketBase instance at base_url is reachable and healthy."""
    import httpx  # type: ignore[import-untyped]  # noqa: PLC0415

    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/health", timeout=10)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def create_collections(base_url: str, admin_token: str) -> dict[str, object]:
    """Idempotently create every assurance collection in PocketBase.

    Existing collections (HTTP 400) are silently skipped.
    Returns a summary dict with counts of created vs existing collections.
    """
    import httpx  # type: ignore[import-untyped]  # noqa: PLC0415

    base = base_url.rstrip("/")
    client = httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    created = 0
    existing = 0
    try:
        for collection_name, fields in _COLLECTIONS:
            # Check existence first to avoid misinterpreting 400 validation errors.
            chk = client.get(f"/api/collections/{collection_name}")
            if chk.status_code == 200:
                existing += 1
                logger.info("Collection already exists: %s", collection_name)
                continue
            payload = {
                "name": collection_name,
                "type": "base",
                "schema": fields,
            }
            resp = client.post("/api/collections", json=payload)
            if resp.status_code in (200, 201):
                created += 1
                logger.info("Created collection: %s", collection_name)
            else:
                resp.raise_for_status()
    finally:
        client.close()

    return {
        "status": "ok",
        "collections_created": created,
        "collections_existing": existing,
        "total": len(_COLLECTIONS),
    }
