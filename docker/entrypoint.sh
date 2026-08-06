#!/usr/bin/env sh
# ─────────────────────────────────────────────────────────────────────────────
# Architectonic container entrypoint — fully non-interactive startup.
#
#   1. Resolve configuration + target locations (workspace, settings document)
#      without opening any store.
#   2. Obtain credentials non-interactively (env-provided passphrase/vault).
#   3-5. Discover, preflight, and migrate every existing persisted target
#      (repositories AND operational stores/caches) via `arch-repair upgrade`,
#      then verify by exit state.
#   6. Initialize absent optional stores at current version (not a migration).
#   7. Only then start ordinary connectors: exec the unified backend as PID 1.
#
# No step ever prompts: git auth and the assurance passphrase come from the
# environment, and the process has no TTY (isatty()==false), so the code paths
# that would otherwise prompt are skipped by design. Startup deliberately has
# no --exclude-target mechanism: excluding a configured active target while
# the software will immediately use it is a contradiction.
# ─────────────────────────────────────────────────────────────────────────────
set -eu

log() { printf '[entrypoint] %s\n' "$*" >&2; }

is_enabled() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        0 | false | no | off | "") return 1 ;;
        *) return 0 ;;
    esac
}

# ── 0. Demo mode: one switch that turns on the three optional setup steps ────
# Each is only DEFAULTED here, so an explicit environment variable still wins and
# a real deployment that never sets ARCH_DEMO is unaffected.
if is_enabled "${ARCH_DEMO:-false}"; then
    ARCH_ENABLE_ASSURANCE="${ARCH_ENABLE_ASSURANCE:-true}"
    ARCH_IMPORT_GUIDANCE="${ARCH_IMPORT_GUIDANCE:-true}"
    ARCH_SEED_ASSURANCE="${ARCH_SEED_ASSURANCE:-true}"
    export ARCH_ENABLE_ASSURANCE ARCH_IMPORT_GUIDANCE ARCH_SEED_ASSURANCE
    log "Demo mode: assurance=$ARCH_ENABLE_ASSURANCE guidance-import=$ARCH_IMPORT_GUIDANCE seed=$ARCH_SEED_ASSURANCE"

    # Populate the demo engagement from the read-only model mount, once per volume.
    # A copy rather than the mount itself, for two reasons that both have to hold: the
    # bundled model is a subdirectory of the source repository, not a git repo of its
    # own — and the upgrade preflight below runs `git status` on the engagement root —
    # and the runtime uid cannot write files the host user owns. The copy is also what
    # keeps a demo from modifying the operator's clone.
    demo_source="${ARCH_DEMO_MODEL_SOURCE:-/opt/demo-model}"
    demo_target="${ARCH_DEMO_ENGAGEMENT:-/data/engagement}"
    if [ -d "$demo_source" ] && [ ! -e "$demo_target/.git" ]; then
        log "Seeding the demo engagement from $demo_source → $demo_target"
        mkdir -p "$demo_target"
        cp -a "$demo_source/." "$demo_target/"
        git -C "$demo_target" init -q
        git -C "$demo_target" add -A
        git -C "$demo_target" \
            -c user.name="${ARCH_GIT_AUTHOR_NAME:-Architectonic Demo}" \
            -c user.email="${ARCH_GIT_AUTHOR_EMAIL:-demo@example.invalid}" \
            commit -q -m "Bundled self-describing model, as shipped"
        log "Demo engagement ready ($(git -C "$demo_target" rev-parse --short HEAD))"
    fi
fi

# ── 1. Configuration + target locations (no store is opened here) ────────────
# SSH remotes. The key path is what an operator knows; the flags are ours, so the
# command is composed here rather than asked for. `accept-new` pins the host key on
# first contact and still refuses a CHANGED one; `BatchMode` fails instead of
# prompting a terminal nobody is watching. ARCH_GIT_SSH_COMMAND remains for a setup
# these flags do not fit, and wins. Exporting only when non-empty keeps an unset
# value from being handed to git as an empty command.
if [ -n "${ARCH_GIT_SSH_COMMAND:-}" ]; then
    export GIT_SSH_COMMAND="$ARCH_GIT_SSH_COMMAND"
    log "Using GIT_SSH_COMMAND from ARCH_GIT_SSH_COMMAND"
elif [ -n "${ARCH_GIT_SSH_KEY:-}" ]; then
    if [ ! -r "$ARCH_GIT_SSH_KEY" ]; then
        log "ERROR: ARCH_GIT_SSH_KEY=$ARCH_GIT_SSH_KEY is not readable in the container."
        log "       Mount the deploy key read-only at that path — see docker-compose.yml."
        exit 1
    fi
    export GIT_SSH_COMMAND="ssh -i $ARCH_GIT_SSH_KEY -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    log "Using SSH deploy key $ARCH_GIT_SSH_KEY for git remotes"
fi

WORKSPACE_CONFIG="${ARCH_WORKSPACE_CONFIG:-/app/arch-workspace.yaml}"
if [ -f "$WORKSPACE_CONFIG" ] && grep -q "your\.git\.host" "$WORKSPACE_CONFIG"; then
    # Fail fast and SAY WHY: without this, arch-init dies on DNS for the template's
    # fake host and the restart policy turns one config mistake into an error loop.
    log "ERROR: $WORKSPACE_CONFIG still contains the shipped placeholder remote 'your.git.host'."
    log "       This file is a template — it cannot be used as-is."
    log "       Fix one of:"
    log "         * edit the 'url:' lines in the mounted workspace file"
    log "           (default: ./arch-workspace.server.yaml next to docker-compose.yml),"
    log "         * point ARCH_WORKSPACE_FILE in .env at your own workspace file,"
    log "         * or use the bundled local model instead of git remotes — see the"
    log "           commented 'local:' variant inside that file."
    exit 1
fi
if [ -f "$WORKSPACE_CONFIG" ]; then
    log "Resolving workspace from $WORKSPACE_CONFIG"
    init_args=""
    is_enabled "${ARCH_INIT_ENGAGEMENT_IF_EMPTY:-true}" && init_args="$init_args --initialize-engagement-repo-if-empty"
    is_enabled "${ARCH_INIT_ENTERPRISE_IF_EMPTY:-true}" && init_args="$init_args --initialize-enterprise-repo-if-empty"
    log "Workspace init flags:${init_args:- (none)}"
    # shellcheck disable=SC2086
    arch-init --config "$WORKSPACE_CONFIG" $init_args
else
    log "No workspace config at $WORKSPACE_CONFIG — relying on ARCH_REPO_ROOT/ARCH_ENTERPRISE_ROOT"
fi

# The container's live settings document is the deployment identity. Upgrade
# discovery and the runtime read the SAME document through ARCH_SETTINGS_PATH,
# so both resolve byte-identical canonical store/cache paths. (Distinct from
# ARCH_SETTINGS_FILE, which is a host-side Compose bind-mount source.)
SETTINGS_PATH="/app/config/settings.yaml"
export ARCH_SETTINGS_PATH="$SETTINGS_PATH"

# Reconcile the module-enabled flag with the toggle every start so the state is
# deterministic regardless of what a previous run wrote to settings.yaml.
ASSURANCE_ON="${ARCH_ENABLE_ASSURANCE:-false}"
if [ -f "$SETTINGS_PATH" ]; then
    ARCH_ASSURANCE_ON="$ASSURANCE_ON" \
    ARCH_MAX_CLASSIFICATION="${ARCH_MAX_CLASSIFICATION:-}" \
    python - "$SETTINGS_PATH" <<'PY'
import os, sys, yaml
path = sys.argv[1]
data = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
data.setdefault("modules", {}).setdefault("assurance", {})["enabled"] = (
    os.environ["ARCH_ASSURANCE_ON"] == "true"
)
tlp = os.environ.get("ARCH_MAX_CLASSIFICATION", "")
if tlp:
    data.setdefault("storage", {}).setdefault("assurance", {})["max_classification"] = tlp
with open(path, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, default_flow_style=False, allow_unicode=True)
PY
fi

if [ "$ASSURANCE_ON" = "true" ]; then
    store="${ARCH_ASSURANCE_STORE_BACKEND:-sqlcipher}"
    signals="${ARCH_ASSURANCE_SIGNALS_BACKEND:-sqlcipher-colocated}"
    archive="${ARCH_ASSURANCE_ARCHIVE_BACKEND:-standard}"
    # 'persistent' rather than the code default 'manual', and the container is the reason. Under
    # 'manual' a newly started process opens nothing until someone authorizes it — which is right on
    # a workstation, where a restart is a human act. Here the process that starts is `arch-backend`
    # at the end of this script, and there is nobody inside the container to authorize it, so the
    # store would stay locked after every `docker compose up` and every restart. Set explicitly
    # rather than inherited so the deployment states its own posture; override with
    # ARCH_ASSURANCE_ACTIVATION_POLICY=manual to require a deliberate
    # `docker compose exec … arch-assurance unlock` instead.
    policy="${ARCH_ASSURANCE_ACTIVATION_POLICY:-persistent}"
    log "Assurance enabled — store=$store signals=$signals archive=$archive activation=$policy"
    # Assert the env-selected backends and activation policy into the settings document
    # (merge: leaves max_classification and other declarative keys untouched).
    arch-assurance use-backend "$store" --signals "$signals" --archive-backend "$archive" \
        --activation-policy "$policy" >/dev/null
fi

# ── 2. Credentials (non-interactive; never logged) ───────────────────────────
if [ "$ASSURANCE_ON" = "true" ] && [ "${ARCH_ASSURANCE_STORE_BACKEND:-sqlcipher}" = "sqlcipher" ] \
    && [ -z "${ARCH_ASSURANCE_MASTER_PASSWORD:-}" ]; then
    log "ERROR: ARCH_ENABLE_ASSURANCE=true with sqlcipher requires ARCH_ASSURANCE_MASTER_PASSWORD"
    exit 1
fi

# ── 3–5. Discover + preflight + migrate every existing target, then verify ───
# Runs before the backend starts, so the guard's "no backend may be serving the
# target repo" check always passes in this single-container deployment, and a
# deployment that is already current is a true no-op (no writes) — safe on every
# restart. Opt out with ARCH_REPAIR_UPGRADE=false (e.g. to defer to a manually
# run `arch-repair upgrade`). Exit-state mapping (readiness reads the report
# state): 0 → proceed; 1 repository step errors, 3 unresolved blocking
# migration, 20 partial apply, 21 infrastructure failure → halt with the report.
if is_enabled "${ARCH_REPAIR_UPGRADE:-true}"; then
    upgrade_roots=""
    if [ -f "$WORKSPACE_CONFIG" ]; then
        upgrade_roots="--workspace $(dirname "$WORKSPACE_CONFIG")"
    else
        [ -n "${ARCH_REPO_ROOT:-}" ] && upgrade_roots="$upgrade_roots --repo-root $ARCH_REPO_ROOT"
        [ -n "${ARCH_ENTERPRISE_ROOT:-}" ] && upgrade_roots="$upgrade_roots --repo-root $ARCH_ENTERPRISE_ROOT"
    fi
    upgrade_args="--commit --settings $SETTINGS_PATH $upgrade_roots"
    log "Upgrading persisted formats (arch-repair upgrade $upgrade_args)"
    rc=0
    # shellcheck disable=SC2086
    arch-repair upgrade $upgrade_args || rc=$?
    case "$rc" in
        0) log "Persisted formats current — proceeding" ;;
        1) log "HALT: repository upgrade steps reported errors (exit 1) — see report above"; exit 1 ;;
        3) log "HALT: unresolved blocking migration (exit 3) — nothing was written; resolve the listed choices"; exit 3 ;;
        20) log "HALT: partial apply (exit 20) — some targets committed; re-run to resume, see report"; exit 20 ;;
        21) log "HALT: infrastructure failure before any commit (exit 21) — see report"; exit 21 ;;
        *) log "HALT: arch-repair upgrade exited $rc"; exit "$rc" ;;
    esac
else
    log "Persisted-format upgrade skipped (ARCH_REPAIR_UPGRADE=false)"
fi

# ── 5b. Authoring guidance (before the backend: the overlay is read at bootstrap) ─
# Never fatal. A backend that refuses to start because a guidance fetch failed is
# strictly worse than one whose authoring surfaces report guidance as not loaded —
# which they do explicitly, so an empty overlay is visible rather than silent.
if is_enabled "${ARCH_IMPORT_GUIDANCE:-false}"; then
    guidance_cache="${HOME:-/home/arch}/.config/arch-repo/guidance-cache"
    if [ -d "$guidance_cache" ] && [ -n "$(ls -A "$guidance_cache" 2>/dev/null)" ] \
       && ! is_enabled "${ARCH_IMPORT_GUIDANCE_FORCE:-false}"; then
        log "Authoring guidance already imported ($guidance_cache) — skipping the fetch"
    elif arch-import-guidance; then
        log "Authoring guidance imported"
    else
        log "WARNING: guidance import failed — the authoring surfaces will report guidance as not loaded"
    fi
fi

# ── 6. Initialize absent optional stores at current version (not a migration) ─
if [ "$ASSURANCE_ON" = "true" ]; then
    store="${ARCH_ASSURANCE_STORE_BACKEND:-sqlcipher}"
    signals="${ARCH_ASSURANCE_SIGNALS_BACKEND:-sqlcipher-colocated}"
    archive="${ARCH_ASSURANCE_ARCHIVE_BACKEND:-standard}"
    case "$store" in
        sqlcipher)
            st="$(arch-assurance status 2>/dev/null | awk '/^status:/ {print $2}')"
            store_created=false
            if [ "$st" = "not_initialised" ] || [ -z "$st" ]; then
                log "Initialising SQLCipher assurance store"
                arch-assurance init --backend sqlcipher --signals "$signals" --archive-backend "$archive"
                store_created=true
            fi
            # Idempotent: verifies the key and sets the activation gate. It cannot authorize the
            # backend, which does not exist yet — this script `exec`s it below, as a new process.
            # What opens that process's store is the activation policy asserted above reading this
            # gate, which is why 'manual' would leave a container locked however often this ran.
            if arch-assurance unlock; then
                case "${ARCH_ASSURANCE_ACTIVATION_POLICY:-persistent}" in
                    persistent)
                        log "Assurance store activated; the backend will open it from the gate on start"
                        ;;
                    *)
                        log "Assurance store activated, but activation_policy is not 'persistent' — the backend will start LOCKED. Run 'arch-assurance unlock' inside the container to authorize it."
                        ;;
                esac
            else
                log "WARNING: assurance unlock failed — store stays locked (fail-closed)"
            fi
            # Seeding REPLACES store content, so it is confined to a store this run
            # created. On any later start the volume holds whatever the operator has
            # since authored, and re-seeding would silently discard it.
            if is_enabled "${ARCH_SEED_ASSURANCE:-false}"; then
                if [ "$store_created" != "true" ]; then
                    log "Assurance store already existed — not seeding (a seed replaces its contents)"
                elif arch-assurance seed; then
                    log "Assurance store seeded from the engagement's bundled analysis"
                else
                    log "WARNING: assurance seed failed — the store is initialised but empty"
                fi
            fi
            ;;
        private-git | pocketbase)
            log "NOTE: store '$store' requires a one-time bootstrap — see docs/reference/docker-compose.md"
            ;;
        *)
            log "WARNING: unknown assurance store backend '$store'"
            ;;
    esac
fi

# ── 7. Start the unified backend ─────────────────────────────────────────────
# ── 5c. Warm the verification cache ──────────────────────────────────────────
# The first whole-repository verification is a full pass and takes minutes on a model of
# any size; every later one reuses the cached results and takes seconds. Left cold, that
# cost lands on whoever first clicks Verify — for a demo, the worst possible moment.
#
# Built here rather than shipped in the image, and that is the point: the cache records
# the absolute paths it verified, and the demo seeds the model into a volume at a path the
# image build cannot know. Warming in place, after seeding, means the cache can only ever
# describe this container's actual repository — it cannot drift from what it caches,
# because it is derived from it seconds earlier.
#
# Never fatal, and skipped by default outside the demo: a backend that refuses to start
# because a warm-up failed is strictly worse than a slow first verification.
if is_enabled "${ARCH_WARM_VERIFY_CACHE:-${ARCH_DEMO:-false}}"; then
    log "Warming the verification cache (first pass is full; later passes reuse it)"
    if python -c "
from pathlib import Path
from src.infrastructure.write.artifact_write.verify import collect_verification_errors
import os
root = Path(os.environ.get('ARCH_REPO_ROOT') or '.').resolve()
collect_verification_errors(root, include_diagrams=True)
" >/dev/null 2>&1; then
        log "Verification cache warm"
    else
        log "WARNING: verification warm-up did not complete — the first verify will be a full pass"
    fi
fi

log "Starting arch-backend on 0.0.0.0:${ARCH_PORT:-8000}"
# shellcheck disable=SC2086
exec arch-backend --host 0.0.0.0 ${ARCH_PORT:+--port "$ARCH_PORT"} \
    ${ARCH_READ_ONLY:+--read-only} \
    ${ARCH_ADMIN_MODE:+--admin-mode} \
    "$@"
