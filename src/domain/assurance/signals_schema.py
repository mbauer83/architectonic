"""Security-signals schema: versioned DDL shared by the runtime stores and the
operational upgrade step.

Version 1 is the empty baseline (a fresh store carries no signal tables until a
migration runs). Version 2 creates the signal-snapshot aggregate — the sole signals
model. The list is append-only — never edit a shipped entry; add a new version.

The single exception on record: version 2's table and column names were rewritten
in place (``security_refresh_runs``/``run_id`` → ``security_signal_snapshots``/
``snapshot_id``) rather than added as version 3, because the product is pre-alpha
with no assurance user and no data to preserve. A store stamped version 2 under the
old names is therefore NOT upgradable — it is detected and reported as needing
recreation (see the signals snapshot-schema upgrade step). Do not treat this as a
precedent once any store holds real data.
"""

from __future__ import annotations

# Connection PRAGMAs applied on every signals-store open: WAL durability and FK
# enforcement. Kept separate from the table DDL so opening a store never depends on
# any particular table definition.
SIGNALS_PRAGMAS_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
"""

_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS security_signal_snapshots (
    snapshot_id            TEXT PRIMARY KEY,
    anchor_entity_id       TEXT NOT NULL,
    request_id             TEXT NOT NULL,
    request_payload_digest TEXT NOT NULL,
    bom_digest             TEXT NOT NULL DEFAULT '',
    bom_serial             TEXT,
    bom_version            TEXT,
    generator_metadata     TEXT NOT NULL DEFAULT '{}',
    source_metadata        TEXT NOT NULL DEFAULT '{}',
    diagnostics            TEXT NOT NULL DEFAULT '{}',
    status                 TEXT NOT NULL,
    started_at             TEXT NOT NULL,
    completed_at           TEXT,
    activated_at           TEXT,
    superseded_at          TEXT,
    failed_at              TEXT,
    failure_reason         TEXT,
    tlp                    TEXT NOT NULL DEFAULT 'TLP:AMBER',
    UNIQUE (anchor_entity_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_snapshot_per_anchor
    ON security_signal_snapshots(anchor_entity_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_snapshots_anchor_status
    ON security_signal_snapshots(anchor_entity_id, status);

CREATE TABLE IF NOT EXISTS snapshot_components (
    component_id        TEXT PRIMARY KEY,
    snapshot_id         TEXT NOT NULL,
    source_component_id TEXT NOT NULL DEFAULT '',
    bom_ref             TEXT NOT NULL DEFAULT '',
    purl           TEXT,
    cpe            TEXT,
    name           TEXT NOT NULL,
    version        TEXT,
    component_type TEXT,
    group_name     TEXT,
    directness     TEXT NOT NULL DEFAULT 'unknown',
    tlp            TEXT NOT NULL DEFAULT 'TLP:AMBER',
    FOREIGN KEY (snapshot_id) REFERENCES security_signal_snapshots(snapshot_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_snapshot_components_snapshot ON snapshot_components(snapshot_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshot_components_source
    ON snapshot_components(snapshot_id, source_component_id);

CREATE TABLE IF NOT EXISTS canonical_vulnerabilities (
    canonical_id TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    merged_into  TEXT
);

CREATE TABLE IF NOT EXISTS vulnerability_aliases (
    alias        TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (canonical_id) REFERENCES canonical_vulnerabilities(canonical_id)
);

CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON vulnerability_aliases(canonical_id);

CREATE TABLE IF NOT EXISTS snapshot_vulnerability_findings (
    finding_id                 TEXT PRIMARY KEY,
    snapshot_id                TEXT NOT NULL,
    component_id               TEXT NOT NULL,
    canonical_vulnerability_id TEXT NOT NULL,
    severity_band              TEXT,
    cvss_score                 REAL,
    cvss_vector                TEXT,
    severity_source            TEXT,
    applicability              TEXT NOT NULL DEFAULT 'applicable',
    provenance                 TEXT NOT NULL DEFAULT '{}',
    tlp                        TEXT NOT NULL DEFAULT 'TLP:AMBER',
    UNIQUE (snapshot_id, component_id, canonical_vulnerability_id),
    FOREIGN KEY (snapshot_id) REFERENCES security_signal_snapshots(snapshot_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES snapshot_components(component_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_findings_snapshot ON snapshot_vulnerability_findings(snapshot_id);

CREATE TABLE IF NOT EXISTS vex_assessments (
    assessment_id              TEXT PRIMARY KEY,
    anchor_entity_id           TEXT NOT NULL,
    canonical_component_id     TEXT NOT NULL,
    canonical_vulnerability_id TEXT NOT NULL,
    revision                   INTEGER NOT NULL,
    disposition                TEXT NOT NULL,
    justification              TEXT NOT NULL DEFAULT '',
    author                     TEXT NOT NULL,
    source                     TEXT NOT NULL DEFAULT '',
    created_at                 TEXT NOT NULL,
    tlp                        TEXT NOT NULL DEFAULT 'TLP:AMBER',
    UNIQUE (anchor_entity_id, canonical_component_id, canonical_vulnerability_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_vex_key
    ON vex_assessments(anchor_entity_id, canonical_component_id, canonical_vulnerability_id);
"""

#: Name the VEX column after the vocabulary it holds: the four values are OpenVEX's own
#: ``status`` set, and ``disposition`` matched no standard while colliding with the unrelated
#: disposition an assurance constraint carries.
#:
#: Added as a new version rather than by editing version 2's DDL in place. Editing shipped DDL
#: leaves an existing store stamped current while carrying the old shape, which the migration
#: loop then correctly skips — the failure mode this schema has already suffered once, and the
#: reason ``_signals_migrations`` has to detect and explain it.
_VEX_STATUS_RENAME_DDL = """
ALTER TABLE vex_assessments RENAME COLUMN disposition TO vex_status;
"""

SIGNALS_MIGRATIONS: list[tuple[int, str]] = [
    (2, _SNAPSHOT_DDL),
    (3, _VEX_STATUS_RENAME_DDL),
]

SIGNALS_SCHEMA_VERSION = 3

#: The version that introduced the signal-snapshot tables. A store stamped at or beyond this must
#: carry them, which is what makes a store stamped here but holding the pre-rename tables
#: detectable. Deliberately its own constant rather than "the current version": tying the check to
#: whichever version happens to be current makes every later migration silently reclassify a
#: pre-rename store as merely outdated, and then try to migrate a schema that has no upgrade path.
SNAPSHOT_TABLES_VERSION = 2


def signals_migration_statements(ddl: str) -> list[str]:
    return [stmt.strip() for stmt in ddl.split(";") if stmt.strip()]
