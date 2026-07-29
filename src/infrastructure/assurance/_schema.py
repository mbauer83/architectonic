from src.domain.assurance.uca_guidewords import LEGACY_GUIDEWORD_SLUGS

"""SQLCipher DDL for the confidential assurance store.

Applied at store initialisation and on each unlock (idempotent — IF NOT EXISTS).
"""

# Connection PRAGMAs applied on every assurance-store open, following the signals store.
# Kept out of the table DDL for two reasons: these are per-connection settings, so a script run
# once would not reach the other threads' connections, and `PRAGMA foreign_keys` is a no-op
# inside a transaction, so declaring it alongside the CREATE statements left it off everywhere.
# With it off, deleting a node removed the node and left its edges behind — dangling rows no
# navigation surface shows and only the verifier reports.
#
# `temp_store` and `secure_delete` state guarantees that were previously true only by accident.
#
# SQLCipher encrypts the database and its write-ahead log. It does not encrypt a temp b-tree that
# SQLite spills for a sort or a join, because SQLite writes that outside the encryption boundary. In
# the build shipped today that never happens — the wheel compiles `SQLITE_TEMP_STORE=2`, so memory is
# already the default, and SQLCipher forces secure delete on for an encrypted database. Neither
# property was requested by this codebase, asserted anywhere, or true of any build but this one.
#
# That is the whole reason they are written here: a different wheel — another platform, a distribution
# build, a later version — may ship `SQLITE_TEMP_STORE=1`, and the store would then write assurance
# content to disk in the clear, past every gate, in a file nothing here creates deliberately, with
# nothing anywhere noticing. Stating the pragma turns a property of the dependency into a property of
# the store, and the suite that reads it back turns that into a verified one. The public artifact
# index has always set `temp_store`; the encrypted store is the one place it guards confidentiality
# rather than speed.
#
# Deliberately NOT set: `cipher_memory_security`. It wipes freed allocations, which guards against
# reading secrets out of process memory — an exposure this project accepts for an already-authorized
# user rather than pays for.
ASSURANCE_PRAGMAS_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;
PRAGMA secure_delete = ON;
"""

ASSURANCE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Filing, one level above analyses. Flat by decision: a group holds analyses and nothing else,
-- because the nesting an architecture project needs comes from the ontology's domains, and an
-- analysis already supplies the middle level here.
CREATE TABLE IF NOT EXISTS assurance_groups (
    group_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assurance_analyses (
    analysis_id            TEXT PRIMARY KEY,
    group_id               TEXT,
    name                   TEXT NOT NULL,
    method                 TEXT NOT NULL,
    architecture_anchor_id TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL DEFAULT 'draft',
    tlp                    TEXT NOT NULL DEFAULT 'TLP:WHITE',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assurance_nodes (
    node_id         TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',
    tlp             TEXT NOT NULL DEFAULT 'TLP:WHITE',
    concern_class   TEXT,
    disposition     TEXT,
    uca_type        TEXT,
    failure_type    TEXT,
    mode            TEXT,
    binding_status  TEXT,
    node_role       TEXT,
    analysis_id     TEXT,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    content_text    TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    created_by      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS assurance_edges (
    edge_id         TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    conn_type       TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES assurance_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES assurance_nodes(node_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS arch_refs (
    assurance_node_id TEXT NOT NULL,
    arch_artifact_id  TEXT NOT NULL,
    ref_type          TEXT NOT NULL,
    resolved_at       TEXT,
    PRIMARY KEY (assurance_node_id, arch_artifact_id, ref_type)
);

CREATE TABLE IF NOT EXISTS audit_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    operation    TEXT NOT NULL,
    node_id      TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    prev_hash    TEXT NOT NULL DEFAULT '',
    entry_hash   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baselines (
    baseline_id TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    head_seq    INTEGER NOT NULL,
    head_hash   TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    analysis_id TEXT
);

-- Participation, as distinct from authorship.
--
-- `assurance_nodes.analysis_id` is PROVENANCE: the analysis that authored a node, single-valued
-- and fixed. This table is PARTICIPATION: the analyses that draw on it. The distinction is what
-- makes STPA→FMEA synergy possible without duplication — an FMEA can enumerate failure modes
-- against the control-structure nodes an STPA identified, referencing them rather than copying
-- them, and both analyses keep seeing the same entity. Collapsing the two would force a node to
-- belong to exactly one analysis, which designs the reuse out.
-- The cascade states the intent for stores created from this schema onwards: a membership is
-- meaningless once the node it names is gone. It is NOT the mechanism deletion relies on.
-- SQLite cannot retrofit a foreign key onto an existing table, so every store initialised before
-- this constraint existed — including the shipped one — would keep orphaning memberships if the
-- declaration were the only guard. `delete_node` therefore removes memberships and `arch_refs`
-- explicitly, in all four backends, which is what actually holds for old and new stores alike.
-- `arch_refs` is deliberately left without a foreign key rather than gaining one here: a
-- constraint only new stores enforce turns one class of bug into a difference between two
-- store ages, and the explicit deletion already covers both.
CREATE TABLE IF NOT EXISTS assurance_analysis_members (
    analysis_id TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (analysis_id, node_id),
    FOREIGN KEY (node_id) REFERENCES assurance_nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_members_node ON assurance_analysis_members(node_id);

CREATE INDEX IF NOT EXISTS idx_nodes_type     ON assurance_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_status   ON assurance_nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_cc       ON assurance_nodes(concern_class);
CREATE INDEX IF NOT EXISTS idx_analyses_method ON assurance_analyses(method);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON assurance_analyses(status);
CREATE INDEX IF NOT EXISTS idx_edges_source   ON assurance_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target   ON assurance_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type     ON assurance_edges(conn_type);
CREATE INDEX IF NOT EXISTS idx_refs_arch      ON arch_refs(arch_artifact_id);
CREATE INDEX IF NOT EXISTS idx_audit_seq      ON audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_audit_op       ON audit_log(operation);

CREATE TABLE IF NOT EXISTS dek_store (
    subject_id  TEXT PRIMARY KEY,
    dek_hex     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    shredded_at TEXT
);

CREATE TABLE IF NOT EXISTS legal_holds (
    hold_id     TEXT PRIMARY KEY,
    baseline_id TEXT NOT NULL,
    held_by     TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    released_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_holds_baseline ON legal_holds(baseline_id);

-- One immutable revision per factor judgement, following the VEX assessment pattern: revisions
-- are appended, never updated, and a superseded revision is retained rather than deleted.
--
-- `basis_digest` is part of the KEY, not a staleness flag. A judgement is made against a picture
-- of the model — for severity the reachable losses and their severities, for detectability the
-- detecting controls and their evidence states — and when that picture changes the judgement
-- simply stops applying, leaving the derived value to stand again. Keying it this way is why no
-- flag is needed: applicability is a fact about which basis the row carries, and a judgement made
-- against a different consequence picture can never continue to drive a priority.
--
-- Derived values are NOT stored. They are recomputed on read, and the digest is computed with
-- them, so a stored derived value could only ever go stale in a way nothing would notice.
CREATE TABLE IF NOT EXISTS fmea_factor_assessments (
    node_id        TEXT NOT NULL,
    factor         TEXT NOT NULL,
    basis_digest   TEXT NOT NULL,
    revision       INTEGER NOT NULL,
    value          TEXT NOT NULL,
    justification  TEXT NOT NULL,
    author         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (node_id, factor, basis_digest, revision),
    FOREIGN KEY (node_id) REFERENCES assurance_nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fmea_assessments_node ON fmea_factor_assessments(node_id);
"""

# Applied once after executescript to add columns to existing tables.
# Each entry is executed and OperationalError (duplicate column) is silently ignored.
# Column-adding ALTERs must precede any index that references the new column,
# because the main schema script (which only has IF NOT EXISTS guards) runs first.
ASSURANCE_SCHEMA_MIGRATIONS: list[str] = [
    "ALTER TABLE baselines ADD COLUMN timestamp_token_hex TEXT",
    "ALTER TABLE assurance_nodes ADD COLUMN analysis_id TEXT",
    # The failure-mode columns need ALTERs even though the table above declares them, because
    # `CREATE TABLE IF NOT EXISTS` adds nothing to a table that already exists — so a store created
    # before these columns would never receive them, and the first insert naming one would fail.
    # (The new factor-assessment TABLE needs no entry: an absent table is exactly what
    # `IF NOT EXISTS` creates.)
    "ALTER TABLE assurance_nodes ADD COLUMN failure_type TEXT",
    "ALTER TABLE assurance_nodes ADD COLUMN mode TEXT",
    "CREATE INDEX IF NOT EXISTS idx_nodes_an_type ON assurance_nodes(analysis_id, node_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_an_status ON assurance_nodes(analysis_id, status)",
    # Filing and participation, added together: an existing store gains both or neither.
    "ALTER TABLE assurance_analyses ADD COLUMN group_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_analyses_group ON assurance_analyses(group_id)",
    # `provided` became two guidewords (see src/domain/assurance/uca_guidewords.py). It meant "provided when
    # it should not be", so every existing UCA carrying it is an unsafe-context finding; nothing maps
    # to the new incorrect-command guideword, which had no home before. Idempotent: the legacy values
    # no longer exist after the first run.
    *(
        f"UPDATE assurance_nodes SET uca_type = '{current}' WHERE uca_type = '{legacy}'"
        for legacy, current in LEGACY_GUIDEWORD_SLUGS.items()
    ),
]

# No entry above is added for the failure-mode columns or the factor-assessment table, and that is
# a decision rather than an oversight: no deployment uses this capability, the additions are
# first-run DDL, and the schema script is `IF NOT EXISTS`-guarded throughout, so a development store
# adopts them on its next unlock. A migration entry would be dead code from the day it shipped.
# The version still moves, so a store carries a record of which shape it was created with.
SCHEMA_VERSION = "6"

# Archive-only schema — used when the archive needs a separate local SQLite file
# (non-SQLCipher store backends: pocketbase, private-git).
ARCHIVE_ONLY_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS audit_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    operation    TEXT NOT NULL,
    node_id      TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    prev_hash    TEXT NOT NULL DEFAULT '',
    entry_hash   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baselines (
    baseline_id TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    head_seq    INTEGER NOT NULL,
    head_hash   TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    analysis_id TEXT,
    timestamp_token_hex TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_seq ON audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_audit_op  ON audit_log(operation);
"""
