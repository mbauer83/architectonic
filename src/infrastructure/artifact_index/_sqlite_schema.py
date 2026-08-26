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
    specializations_json TEXT NOT NULL,
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
-- The pad itself, as distinct from the thoughts on it. A pad outlives its notes: a note stops being
-- searchable once it has a model counterpart, so a pad whose thinking has all been lifted has no
-- searchable notes and this row is the only record that the thinking happened.
CREATE TABLE IF NOT EXISTS scratchpads (
    artifact_id TEXT PRIMARY KEY,
    name TEXT NOT NULL, description TEXT NOT NULL, version TEXT NOT NULL,
    status TEXT NOT NULL, meta_ontology TEXT NOT NULL,
    path TEXT NOT NULL, scope TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT 'uncategorized'
);
-- A note has no file of its own: `path` is its scratchpad's, and `artifact_id` is composed. The
-- only record kind whose searchable units live inside another artifact.
CREATE TABLE IF NOT EXISTS scratchpad_notes (
    artifact_id TEXT PRIMARY KEY,
    scratchpad_id TEXT NOT NULL, scratchpad_name TEXT NOT NULL, note_id TEXT NOT NULL,
    title TEXT NOT NULL, body TEXT NOT NULL, element_type TEXT NOT NULL,
    domain TEXT NOT NULL, area TEXT NOT NULL, status TEXT NOT NULL,
    path TEXT NOT NULL, scope TEXT NOT NULL,
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
    specializations_json TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_scratchpads_status ON scratchpads(status);
CREATE INDEX IF NOT EXISTS idx_scratchpads_group ON scratchpads(group_name);
CREATE INDEX IF NOT EXISTS idx_scratchpad_notes_pad ON scratchpad_notes(scratchpad_id);
CREATE INDEX IF NOT EXISTS idx_scratchpad_notes_status ON scratchpad_notes(status);
CREATE INDEX IF NOT EXISTS idx_scratchpad_notes_group ON scratchpad_notes(group_name);
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
-- `host_diagram_id` is UNINDEXED and carried for filtering, not for matching: search visibility
-- turns on whether a record is diagram-owned, and that question has to be answerable *inside* the
-- per-kind `ORDER BY … LIMIT` below. Answering it after the window was allocated is how a search
-- asked for twenty rows returned sixteen — the four it lost were the highest-scoring entity hits,
-- ranked and then discarded by a filter keyed on something the ranking could not see.
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    artifact_id UNINDEXED, name, artifact_type, domain,
    subdomain, keywords, content_text, display_label, host_diagram_id UNINDEXED
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
-- `scratchpad_id` is carried unindexed so a scratchpad's rows can be removed without consulting
-- anything else: an fts5 table has no foreign key, and deleting by a set read from elsewhere leaks
-- rows the moment that elsewhere is wrong.
-- A pad matches on its own name and its own description, and on nothing else. Matching it on its
-- notes' text is the wrong answer 0.7.1 removed, inverted: a pad handed back because one of forty
-- notes mentions a word reads as wrong however it was reached, and the note itself is already
-- returned in that case.
CREATE VIRTUAL TABLE IF NOT EXISTS scratchpads_fts USING fts5(
    artifact_id UNINDEXED, name, description
);
CREATE VIRTUAL TABLE IF NOT EXISTS scratchpad_notes_fts USING fts5(
    -- `scratchpad_name` is UNINDEXED, not merely weighted at nothing. A zero bm25 weight stops a
    -- column contributing to the *rank* and not to the *match*, so with it indexed a note answered
    -- any query its pad's title matched, whatever the note itself said. Finding the pad is a
    -- different question and a note cannot answer it.
    artifact_id UNINDEXED, scratchpad_id UNINDEXED, title, body, element_type, domain,
    scratchpad_name UNINDEXED
);
"""
