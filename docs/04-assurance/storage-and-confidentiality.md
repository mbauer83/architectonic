# Storage & Confidentiality

> Reference for how assurance data is stored, encrypted, archived, and accessed.

- [Store vs. archive](#store-vs-archive)
- [Store backends](#store-backends)
- [Archive backends](#archive-backends)
- [Credential storage](#credential-storage)
- [CLI reference](#cli-reference)
- [Key management & backup](#key-management--backup)

Assurance content is encrypted at rest and confidential by default. The architecture model
in git never holds it; the only link is a one-way reference from an assurance entity to an
architecture entity, which is never reverse-persisted into the model.

&nbsp;

## Store vs. archive

Every deployment runs two components in parallel, configured by separate keys.

| Component | Config key | Default | Role |
|---|---|---|---|
| **Store** (`ConfidentialAssuranceStore`) | `store_backend` | `sqlcipher` | Mutable encrypted workspace for live analysis |
| **Archive** (`AssuranceArchive`) | `archive_backend` | `standard` | Append-only, hash-chained evidence trail |

The store is a fully mutable encrypted graph — create hazards, update status, link controls,
delete drafts. Safety analysis evolves, so the store carries no immutability guarantees by
design.

The archive records every significant operation as a hash-chained entry that is never
modified or deleted. Its purpose is regulatory and forensic: proving after the fact what was
known, when, and in what state — the kind of tamper-evident log the EU AI Act (Art. 12)
expects for high-risk AI systems. It runs automatically alongside the store.

Confidentiality is a store concern; immutability is an archive concern. The two are
configured independently, with one exception: `archive_backend: worm` shares the SQLCipher
database file and therefore requires `store_backend: sqlcipher`. The cloud archive backends
write to their own storage and work with any store backend.

&nbsp;

## Store backends

| `store_backend` | Storage | Best for | System dependency |
|---|---|---|---|
| `sqlcipher` (default) | One AES-256 SQLite file at `.arch-assurance/store.db` | Individuals and small teams in one workspace | `libsqlcipher-dev` |
| `private-git` | Fernet-encrypted `.enc` files in a git-trackable tree (history is ciphertext) | Teams wanting file-level encryption with a diffable history | none (Python `cryptography`) |
| `pocketbase` | A [PocketBase](https://pocketbase.io) REST service | Shared team deployments across workstations | a running PocketBase instance |

```bash
uv run arch-assurance init                       # sqlcipher (default)
uv run arch-assurance init --backend private-git
uv run arch-assurance use-backend pocketbase     # then: uv run arch-backend --restart --daemon
```

Switching backends does not migrate data. Run `arch-assurance export -o backup.json` first
if you need to carry entries across.

**SQLCipher WAL mode.** The SQLCipher backend runs in WAL (Write-Ahead Log) mode, which
creates two sidecar files alongside `store.db`: `store.db-wal` and `store.db-shm`. Both files
are encrypted by SQLCipher to the same standard as the main database — no plaintext assurance
content reaches disk in any of the three files. The sidecar files are covered by the
`.arch-assurance/.gitignore` rules and will never appear as untracked files in the repository.

&nbsp;

## Archive backends

| `archive_backend` | Storage | Immutability mechanism | Dependency |
|---|---|---|---|
| `standard` (default) | Co-located with the store | SHA-256 hash chain (software) | none |
| `worm` | SQLCipher (same DB as store) | Hash chain + per-subject AES-256-GCM DEK + legal holds | `store_backend: sqlcipher` |
| `s3-worm` | Amazon S3 | S3 Object Lock (GOVERNANCE / COMPLIANCE) | `boto3`; bucket with Object Lock |
| `azure-blob-worm` | Azure Blob Storage | Container immutability policy | `azure-storage-blob`, `azure-identity` |

`standard` suits most teams: the hash chain detects tampering and store encryption protects
confidentiality. Move to a WORM backend when you need storage-layer enforcement —
cloud-provider guarantees against deletion even by a compromised account, legal holds that
survive key rotation, per-subject crypto-shredding for GDPR erasure, or RFC 3161 timestamp
tokens for non-repudiation.

```bash
# Local WORM (requires the SQLCipher store)
uv run arch-assurance use-backend sqlcipher --archive-backend worm

# AWS S3 Object Lock (independent of store backend)
uv sync --extra s3-archive
export ARCH_S3_BUCKET="my-worm-bucket"          # Object Lock enabled at bucket creation
export ARCH_S3_OBJECT_LOCK_MODE="GOVERNANCE"    # or COMPLIANCE
uv run arch-assurance use-backend sqlcipher --archive-backend s3-worm

# Azure Blob immutability (independent of store backend)
uv sync --extra azure-archive
export ARCH_AZURE_STORAGE_ACCOUNT="myaccount"
export ARCH_AZURE_CONTAINER="arch-assurance"    # immutability policy applied
uv run arch-assurance use-backend sqlcipher --archive-backend azure-blob-worm
```

The `azure-blob-worm` adapter uses two containers: the archive container (WORM) and a mutable
state container holding the chain head, holds index, and DEKs. Apply the time-based
immutability policy to the archive container only.

&nbsp;

## TLP ceiling and withheld content

Every deployment is configured with a **TLP ceiling** — the highest classification that the
backend will expose over REST and MCP interfaces. Nodes, edges, and analyses above the ceiling
are withheld from all read responses; they are not counted, mentioned, or hinted at in any
response body, count, or finding.

The ceiling is set in `config/settings.yaml`:

```yaml
storage:
  assurance:
    max_classification: TLP:AMBER   # TLP:WHITE | TLP:GREEN | TLP:AMBER | TLP:RED
```

`TLP:RED` (the default) exposes everything the store contains — appropriate for a single
operator who holds the encryption key. Lower values let a team see analysis results without
accessing the most sensitive records, for example when RED entries contain unpublished
vulnerability details or PII.

When the ceiling omits records, the GUI shows a **withheld notice** that names the count and
the ceiling: for example *"3 items withheld above your TLP:AMBER ceiling."* This is the policy
working as intended, not an error. The notice appears in the browse view, node detail, and
assurance lens wherever visible counts are lower than the full store total. It does not reveal
the IDs, names, or contents of the withheld items.

&nbsp;

## Credential storage

The encryption key lives in an OS-appropriate credential backend, selected automatically, and
is never written to disk in plaintext.

| Environment | Backend | Notes |
|---|---|---|
| macOS | macOS Keychain | Always available; no setup |
| WSL2 on Windows | Windows DPAPI | Via `powershell.exe`; user-and-machine-scoped |
| Linux desktop | SecretService (D-Bus) | Needs gnome-keyring or kwallet running |
| Headless Linux / CI | Fernet-encrypted vault | Set `ARCH_ASSURANCE_MASTER_PASSWORD` |

```bash
# Headless / CI
export ARCH_ASSURANCE_MASTER_PASSWORD="your-long-random-passphrase"
uv run arch-assurance init
uv run arch-assurance unlock
```

### Activation

`arch-assurance unlock` does two things. It sets the *setup-confirmed* gate in the keychain,
recording that this store was ceremonially activated — the key was verified and someone
consciously enabled the capability. And it authorizes the backend that is running now, so
`arch-assurance status` reports `unlocked: true` without waiting for a restart.

Whether a *newly started* process opens the store by itself is a separate question, and a
deployment answers it with `storage.assurance.activation_policy`:

| Value | Behaviour | Suits |
|---|---|---|
| `manual` (default) | A new process starts locked. `unlock` authorizes the process that is running, for its lifetime. | A workstation, where a restart is already a human act and walk-up access to an unattended session is the threat. |
| `persistent` | A new process opens the store from the activation gate, until `lock` revokes it. | A server, where an unattended reboot must not take the capability down. |

Under `manual` — the default — restarting the backend leaves the store locked, so run
`arch-assurance unlock` again before expecting the assurance surfaces to answer. An unrecognised
policy value is rejected rather than assumed: a misspelling must not silently grant the more
permissive behaviour.

`arch-assurance lock` revokes access with immediate effect on a running backend, closing the store
rather than waiting for its next start. It clears the activation gate; the key stays in the
keychain, so `unlock` re-enables access without the recovery key.

**What this bounds.** Application-level access, not key extraction. The key remains in the OS
keychain under either policy, so anyone able to read the credential store is unaffected by the
activation policy.

&nbsp;

## CLI reference

| Command | Description |
|---|---|
| `arch-assurance init [--force] [--backend B] [--archive-backend A]` | Create the encrypted store; generate and save the key |
| `arch-assurance unlock` | Set the activation gate and authorize the running backend (reports `unlocked: true`) |
| `arch-assurance lock` | Revoke access with immediate effect; clears the activation gate, key stays in the keychain |
| `arch-assurance status` | Show backends, DB path, key presence, and unlock state |
| `arch-assurance export-key` | Print the recovery key (store offline) |
| `arch-assurance rotate-key` | Generate a new key and re-encrypt the database |
| `arch-assurance backup [--backup-path P]` | Copy the encrypted DB to a timestamped backup |
| `arch-assurance export -o out.json` | Export all data as plaintext JSON |
| `arch-assurance verify` | Backend-aware chain integrity check (all archive backends) |
| `arch-assurance verify-chain` | Verify the audit hash chain (SQLCipher only) |
| `arch-assurance use-backend B [--archive-backend A]` | Switch store and/or archive backend |
| `arch-assurance import FILE [--replace]` | Restore an exported JSON bundle |
| `arch-assurance seed [--with-signals]` | Load the active engagement's bundle (`.arch-repo/assurance-seed.json`), optionally ingesting signals; `--input` overrides |
| `arch-assurance export-aibom` | Emit a CycloneDX 1.6 AI-BOM |
| `arch-assurance scan-ai-candidates` | Heuristic scan of entities for AI-BOM relevance |

&nbsp;

## Key management & backup

The recovery key is a separate randomly generated token that can decrypt the database if the
OS credential entry is lost (for example after migrating machines). Print it once after init
and keep it offline:

```bash
uv run arch-assurance export-key
```

Rotate the key when an operator leaves a team, and save the new recovery key:

```bash
uv run arch-assurance rotate-key
uv run arch-assurance export-key
```

Backups are encrypted with the same key as the live database. Keep at least one backup and
the recovery key in separate, durable locations.

---

*Next: [AI-BOM →](aibom.md)*
