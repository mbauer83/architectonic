"""SQLite DDL for the artifact index in-memory database."""

SCHEMA_SQL = """
PRAGMA journal_mode = MEMORY;
PRAGMA synchronous = OFF;
PRAGMA temp_store = MEMORY;
PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS entities (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL,
    status TEXT NOT NULL, domain TEXT NOT NULL, subdomain TEXT NOT NULL,
    path TEXT NOT NULL, scope TEXT NOT NULL, keywords_json TEXT NOT NULL,
    extra_json TEXT NOT NULL, content_text TEXT NOT NULL,
    display_blocks_json TEXT NOT NULL, display_label TEXT NOT NULL, display_alias TEXT NOT NULL,
    host_diagram_id TEXT,
    group_name TEXT NOT NULL DEFAULT 'uncategorized'
);
CREATE TABLE IF NOT EXISTS connections (
    artifact_id TEXT PRIMARY KEY,
    source TEXT NOT NULL, target TEXT NOT NULL, conn_type TEXT NOT NULL,
    version TEXT NOT NULL, status TEXT NOT NULL, path TEXT NOT NULL,
    scope TEXT NOT NULL, extra_json TEXT NOT NULL, content_text TEXT NOT NULL,
    associated_entities_json TEXT NOT NULL,
    src_multiplicity TEXT NOT NULL, tgt_multiplicity TEXT NOT NULL,
    specialization TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT 'uncategorized'
);
CREATE TABLE IF NOT EXISTS diagrams (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL, name TEXT NOT NULL, diagram_type TEXT NOT NULL,
    version TEXT NOT NULL, status TEXT NOT NULL, path TEXT NOT NULL,
    scope TEXT NOT NULL, extra_json TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT 'uncategorized'
);
CREATE TABLE IF NOT EXISTS documents (
    artifact_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
    path TEXT NOT NULL, scope TEXT NOT NULL, keywords_json TEXT NOT NULL,
    sections_json TEXT NOT NULL, content_text TEXT NOT NULL, extra_json TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT 'uncategorized'
);
CREATE TABLE IF NOT EXISTS entity_context_edges (
    entity_id TEXT NOT NULL, connection_id TEXT NOT NULL, direction_bucket TEXT NOT NULL,
    other_entity_id TEXT NOT NULL, conn_type TEXT NOT NULL,
    connection_status TEXT NOT NULL, connection_version TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    source_name TEXT NOT NULL, target_name TEXT NOT NULL,
    source_artifact_type TEXT NOT NULL, target_artifact_type TEXT NOT NULL,
    source_domain TEXT NOT NULL, target_domain TEXT NOT NULL,
    source_scope TEXT NOT NULL, target_scope TEXT NOT NULL,
    path TEXT NOT NULL, content_text TEXT NOT NULL,
    associated_entities_json TEXT NOT NULL,
    src_multiplicity TEXT NOT NULL, tgt_multiplicity TEXT NOT NULL,
    specialization TEXT NOT NULL,
    PRIMARY KEY (entity_id, connection_id, direction_bucket)
);
CREATE TABLE IF NOT EXISTS entity_context_stats (
    entity_id TEXT PRIMARY KEY,
    conn_in INTEGER NOT NULL DEFAULT 0,
    conn_out INTEGER NOT NULL DEFAULT 0,
    conn_sym INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(artifact_type);
CREATE INDEX IF NOT EXISTS idx_entities_domain ON entities(domain);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_group ON entities(group_name);
CREATE INDEX IF NOT EXISTS idx_entities_host_diagram ON entities(host_diagram_id) WHERE host_diagram_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_connections_source ON connections(source);
CREATE INDEX IF NOT EXISTS idx_connections_target ON connections(target);
CREATE INDEX IF NOT EXISTS idx_connections_type ON connections(conn_type);
CREATE INDEX IF NOT EXISTS idx_connections_status ON connections(status);
CREATE INDEX IF NOT EXISTS idx_connections_group ON connections(group_name);
CREATE INDEX IF NOT EXISTS idx_diagrams_type ON diagrams(diagram_type);
CREATE INDEX IF NOT EXISTS idx_diagrams_status ON diagrams(status);
CREATE INDEX IF NOT EXISTS idx_diagrams_group ON diagrams(group_name);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_group ON documents(group_name);
CREATE INDEX IF NOT EXISTS idx_entity_context_edges_entity
    ON entity_context_edges(entity_id, direction_bucket, connection_id);
CREATE INDEX IF NOT EXISTS idx_entity_context_edges_other ON entity_context_edges(other_entity_id);

CREATE TABLE IF NOT EXISTS attribute_type_refs (
  diagram_id TEXT NOT NULL,
  classifier_local_id TEXT NOT NULL,
  attr_name TEXT NOT NULL,
  type_id TEXT NOT NULL,
  PRIMARY KEY (diagram_id, classifier_local_id, attr_name)
);
CREATE INDEX IF NOT EXISTS idx_attr_type_refs_type ON attribute_type_refs(type_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    artifact_id UNINDEXED, name, artifact_type, domain,
    subdomain, keywords, content_text, display_label
);
CREATE VIRTUAL TABLE IF NOT EXISTS connections_fts USING fts5(
    artifact_id UNINDEXED, source, target, conn_type, content_text
);
CREATE VIRTUAL TABLE IF NOT EXISTS diagrams_fts USING fts5(
    artifact_id UNINDEXED, name, diagram_type, artifact_type, member_names
);
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    artifact_id UNINDEXED, title, doc_type, keywords, content_text
);
"""
