# Installation & Setup

> Full setup, per operating system. For the 60-second path, see the
> [Quickstart in the README](../README.md#quickstart).

- [System requirements](#system-requirements)
- [Per-environment prerequisites](#per-environment-prerequisites) — macOS · Debian/Ubuntu · WSL2 · Docker
- [1. Install Python dependencies](#1-install-python-dependencies)
- [2. Diagram runtime](#2-diagram-runtime)
- [3. Initialize the workspace](#3-initialize-the-workspace)
- [4. Start the backend](#4-start-the-backend)
- [5. Configure MCP access for AI agents](#5-configure-mcp-access-for-ai-agents)
- [6. Build and serve the GUI](#6-build-and-serve-the-gui)
- [7. Quality checks](#7-quality-checks)
- [Running in Docker](#running-in-docker)
- [Assurance store setup](#assurance-store-setup)
- [Deployment topology](#deployment-topology)

For backend ports, log paths, schemata, and storage backends, see
[Configuration Reference](reference/configuration.md).

---

&nbsp;

## System requirements

| Dependency | Minimum | Purpose |
|---|---|---|
| Python | 3.14 | All server and CLI components |
| `uv` | any recent | Python environment and script runner |
| Java | 11 | PlantUML diagram rendering and verification |
| Graphviz | 2.49.0 | Diagram layout engine |
| Node.js | 24 | Frontend development only (not needed to run) |
| npm | 11 | Frontend development only; npm refuses to install the frontend under another major |
| SQLCipher (system lib) | 4 | Assurance store (optional) |

---

&nbsp;

## Per-environment prerequisites

### macOS

```bash
# Core
brew install python@3.14 openjdk graphviz
curl -LsSf https://astral.sh/uv/install.sh | sh

# Frontend development (optional) — the version package.json declares; npm refuses others
brew install node@24

# Assurance store (optional)
brew install sqlcipher
```

Java from Homebrew needs a symlink for the system `java` command:

```bash
sudo ln -sfn $(brew --prefix openjdk)/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk.jdk
```

Assurance-store credentials live in **macOS Keychain** automatically — no extra setup.

### Linux (Debian / Ubuntu)

```bash
# Core
sudo apt-get update
sudo apt-get install -y default-jre graphviz curl

# uv, and Python 3.14 through it (Debian and Ubuntu do not package 3.14)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14

# Frontend development (optional) — use nvm or NodeSource
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs

# Assurance store (optional)
sudo apt-get install -y libsqlcipher-dev
```

For credential storage the assurance store uses **SecretService (D-Bus / gnome-keyring)**
when a desktop session is running. On headless servers (CI, SSH-only), set a master password
instead — see [Assurance: credential storage](04-assurance/storage-and-confidentiality.md#credential-storage).

### WSL2 on Windows

Run every command in the WSL2 Debian/Ubuntu shell and follow the Debian/Ubuntu steps above.

SQLCipher needs the native system library inside WSL2, even though the Windows host has no
equivalent:

```bash
sudo apt-get install -y libsqlcipher-dev
```

Credentials are kept in **Windows DPAPI** through PowerShell interop
(`Export-Clixml` / `Import-Clixml`), encrypting each key with the Windows user's login
credentials — machine-and-user-scoped, with no setup beyond having PowerShell reachable from
WSL2 (the default on Windows 11).

### Docker

No local prerequisites beyond Docker. The image bundles Java, Graphviz, and all Python
dependencies. See [Running in Docker](#running-in-docker).

The assurance store is **not** enabled in the default image because it needs host-level
credential storage. To use it in Docker, mount credentials or supply
`ARCH_ASSURANCE_MASTER_PASSWORD` as an environment variable.

---
> Use `uv sync`, not `pip install`. The `zuban` type checker ships in the `dev`
> dependency group (`uv sync --group dev`, included in `--all-groups`).

> **Running the project's commands.** `uv sync` installs this project's entry points
> (`arch-backend`, `arch-init`, `get-plantuml`, `arch-assurance`, …) into `.venv/`, which is not
> on your `PATH`. Every command below is therefore written as `uv run <command>`, which needs no
> activation and always resolves the project's own environment. If you prefer the bare names,
> activate the environment once per shell — `source .venv/bin/activate` (`.venv\Scripts\activate`
> on Windows) — and drop the `uv run` prefix.

&nbsp;

## 1. Install Python dependencies

```bash
# Everything the backend, the MCP bridges and the CLI need, plus the dev tooling
uv sync

# Runtime only, without pytest, ruff and zuban
uv sync --no-dev

# All dependency groups
uv sync --all-groups

# Cloud archive backends (optional — pick what you need)
uv sync --extra s3-archive        # + boto3 for S3 Object Lock archive
uv sync --extra azure-archive     # + azure-storage-blob + azure-identity for Azure archive
uv sync --extra cloud-archive     # both S3 and Azure
```

The web server, the assurance store's Python bindings and every other runtime dependency are core
dependencies, so a plain `uv sync` is enough to run everything below. The store itself also needs
`libsqlcipher-dev` on the host. The `gui` dependency group is empty and kept only so that
`uv sync --group gui`, written for older installations, still works.

&nbsp;

## 2. Diagram runtime

```bash
# Download and verify plantuml.jar from Maven Central
uv run get-plantuml                   # → plantuml.jar beside pyproject.toml (gitignored)

# Same jar, plus a supported Graphviz — use this instead if your system Graphviz
# is older than 2.49.0 (it builds one from source on Linux, or installs a system
# package elsewhere) and then verifies the pair
uv run get-diagram-runtime

# Verify local Graphviz/PlantUML compatibility for rendering
uv run check-diagram-runtime          # requires Graphviz >= 2.49.0
```

The Java runtime PlantUML runs on is yours to choose: the executable resolves via
`ARCH_JAVA` (explicit path), then `JAVA_HOME`, then `java` on `PATH` — so any
compatible JRE can be substituted without configuration-file changes. Licensing
context for the bundled jar and the JRE is in
[Licensing](reference/licensing.md#bringing-your-own-java-runtime).

&nbsp;

## 3. Initialize the workspace

An `arch-workspace.yaml` at the workspace root declares the two repositories. The checkout ships
one that resolves the bundled self-model and clones the public demo enterprise repository, so
`uv run arch-init` works on a fresh clone as it is.

To work on your own repositories, edit that file. A repository is declared in one of two forms:

- `local:` names a directory that already holds an architecture repository (a `model/` directory,
  or `projects/<slug>/model/`). `arch-init` does not create one.
- `git:` names a remote and where to clone it. A new repository starts as an empty remote — a bare
  repository, or an empty project on your git host — which `arch-init` scaffolds and publishes.

```yaml
engagement:
  git: { url: "https://git.example.org/arch/engagement.git", branch: main, path: .arch/repos/engagement }

enterprise:
  git: { url: "https://git.example.org/arch/enterprise.git", branch: main, path: .arch/repos/enterprise }

backend:
  port: 8000          # optional: pin the backend's port (see §4)
```

Then resolve and validate it:

```bash
uv run arch-init                      # reads arch-workspace.yaml, writes .arch/init-state.yaml

# Remotes that are still empty: scaffold and publish both in one run
uv run arch-init --initialize-engagement-repo-if-empty --initialize-enterprise-repo-if-empty
```

Pass both flags in one command when both remotes are empty. With one flag, `arch-init` publishes that
repository and then stops at the other one, reporting the flag it needs.

The edits you make to `arch-workspace.yaml` and `config/settings.yaml` are this installation's
configuration. Leave them as uncommitted changes: `arch-update` keeps them when it moves the
checkout to a release, and merges them onto the release's version where the release changes one of
those files (see [Updating an installation](reference/software-update.md#your-configuration)).

For workspaces that hop between multiple engagement repos, and for `arch-switch-engagement`
usage, see [CLI & Backend Reference](reference/cli-and-backend.md).

**Optional: import authoring guidance.** The per-concept "create when / never create
when" guidance text is license-separated and ships empty — until you import it, the
authoring surfaces state explicitly that guidance is not loaded (they never fall
silently blank). To load it:

```bash
uv run arch-import-guidance              # the source configured in config/settings.yaml
uv run arch-import-guidance --dry-run    # report what an import would write, write nothing
```

The overlay is read once at bootstrap, so restart the backend afterwards — or import before
starting it, as the README quickstart does.

The import writes to `~/.config/arch-repo/guidance-cache`, which every installation of the same
operating-system user reads unless it has its own. To give an installation its own cache, set
`deployment.guidance_cache_root` in its settings document; the backend, the import and
`arch-repair upgrade` all use that path. An update never puts the shared cache back to an earlier
state, because other installations read it.

See [Authoring guidance](05-extensibility/guidance.md) for the format and layering.

&nbsp;

## 4. Start the backend

`arch-backend` serves the REST API and the MCP endpoints. It also serves the GUI at `/` once
the SPA has been built into `tools/gui/dist/` (see [§6](#6-build-and-serve-the-gui)); a build made
while the backend runs is served without a restart. Until then `/` answers 404 with a note that the
GUI has not been built. The backend never builds or runs the frontend itself.

If you create the assurance store (see [Assurance store setup](#assurance-store-setup)), do it
before starting the backend. The assurance modules register when the backend starts, so a store
created afterwards needs `uv run arch-backend --restart --daemon` and `uv run arch-assurance unlock`;
`arch-assurance init` says so when it finds a backend running.

```bash
# Backend: REST API at :8000, MCP at :8000/mcp/{read,write}; GUI at / if built (§6)
uv run arch-backend --daemon

# Inspect / stop / restart
uv run arch-backend --status
uv run arch-backend --stop
uv run arch-backend --restart --daemon
```

The port is `backend.port` from `arch-workspace.yaml` when set there. Otherwise the backend takes
8000, or a port derived from its repository paths (8100–8499) when another workspace's backend holds
8000, and prints the address; see [Configuration](reference/configuration.md).

`--daemon` starts the backend in a new session, redirects stdin from `/dev/null`, and writes
to `backend.log_path`. This avoids the shell job-control stops that can happen with a raw
`arch-backend &` when a background process reads from the terminal. (`arch-backend &` still
works and detaches stdin when it detects a background TTY job; `--daemon` is the preferred
operational form.)

If the GUI hangs on "Loading...", diagnose the transport before assuming a lock — see
[CLI & Backend Reference](reference/cli-and-backend.md#troubleshooting).

&nbsp;

## 5. Configure MCP access for AI agents

Add the servers to `.mcp.json` (Claude Code) or `.vscode/mcp.json` (VS Code):

```json
{
  "mcpServers": {
    "arch-repo-read":  { "command": "uv", "args": ["run", "arch-mcp-stdio-read"] },
    "arch-repo-write": { "command": "uv", "args": ["run", "arch-mcp-stdio-write"] }
  }
}
```

The MCP surface is split into two servers so an agent can be constrained by capability
(read-only vs. authoring). Both STDIO bridges auto-start the unified backend when needed and
connect over HTTP, so GUI and MCP traffic share the same in-process cache and write queue.

To attach to an already-running external backend instead, set
`"env": { "ARCH_MCP_BACKEND_URL": "http://127.0.0.1:8000" }` on the server entry.

For the optional assurance MCP servers, see
[Assurance MCP tools](04-assurance/mcp-tools.md). For inspecting the live tool surface with
the MCP Inspector, see [Interfaces & MCP](03-modeling/interfaces-and-mcp.md).

&nbsp;

## 6. Build and serve the GUI

The frontend is a Vue single-page app. It is **not** a runtime service the backend launches —
you either compile it to static files that the backend serves, or run the Vite dev server
during development. Pick one:

**Serve the GUI from the backend (production / normal use).** Build once; the backend serves the
result at `/`, whether it was started before or after the build:

```bash
cd tools/gui
npm ci                 # installs exactly what package-lock.json names
npm run build          # → tools/gui/dist/  (served by arch-backend at /)
cd ../..
```

`npm ci` refuses to run on a Node or npm major other than the ones `package.json` declares
(Node 24, npm 11). With nvm: `nvm install 24 && nvm use 24`.

Re-run `npm run build` after pulling frontend changes. The Docker image performs this build
automatically, so containerised deployments need no manual step. From release 0.10.0 on,
[`arch-update`](reference/software-update.md) moves the checkout to a published release, installs
the built GUI the release carries and runs the data upgrade, so none of this is repeated by hand.

**Develop with hot-reload (frontend work).** Run the Vite dev server instead of building; it
proxies API calls to the backend on :8000:

```bash
cd tools/gui
npm ci
npm run dev
# → open http://localhost:5173  (API + MCP proxied to arch-backend on :8000)
```

If you only need the REST and MCP APIs, you can skip this step entirely.

&nbsp;

## 7. Quality checks

Python lint and type checks from the workspace root:

```bash
uv run ruff check src
uv run zuban check
uv run pytest --tb=short -q
```

`ruff` covers import sorting plus core error detection and ignores the model/content repos,
the test tree, and the Vue tree. `zuban` runs in its default mode (stricter than mypy on some checks) against `src/`.

Coverage is opt-in (the default run stays fast):

```bash
uv run pytest --cov                       # terminal summary with missing lines
uv run pytest --cov --cov-report=html     # browsable htmlcov/ report
```

One run yields three figures because branch coverage is enabled. The **canonical, reported
number is statement/line coverage (~79%)** — this is what Codecov shows. coverage.py's own
headline (`percent_covered`, and therefore the `fail_under` ratchet) is the **branch-inclusive
combined** metric (~76%); branch-only coverage is ~66%. Quote the same basis everywhere to
avoid apparent discrepancies between the badge and a local run.

Frontend lint and type checks from `tools/gui`:

```bash
cd tools/gui
npm run lint
npm run typecheck
```

The frontend uses ESLint 10 with the Vue and TypeScript flat-config presets plus type-aware
rules, and `vue-tsc` / `tsc` for application and Vite config type-checking.

---

&nbsp;

## Running in Docker

A multi-stage image bundles the SPA, the Python backend, and the diagram runtime
(Java, Graphviz, fonts). The whole stack — GUI, REST, and all MCP endpoints — runs as one
container on port 8000, started fully non-interactively (git and assurance credentials come
from the environment).

```bash
cp .env.example .env                 # secrets & toggles
$EDITOR arch-workspace.server.yaml   # point at your git repos
docker compose up -d --build         # → http://localhost:8000  (assurance OFF by default)
```

Profiles add a TLS reverse proxy (`proxy`) and a PocketBase assurance store (`pocketbase`);
assurance, storage backends, the TLP ceiling, and VPN/proxy setup are all configured
declaratively. The full guide — profiles, the storage matrix, non-interactive secrets, and
connecting MCP clients over the network — is in
[Docker Compose Deployment](reference/docker-compose.md).

To attach a host MCP client to the Dockerised backend, point it at the served endpoints
(`https://<host>/mcp/read`, …) or set `ARCH_MCP_BACKEND_URL=http://127.0.0.1:8000` so the
STDIO bridge attaches to the published port instead of starting its own.

---

&nbsp;

## Assurance store setup

The assurance store is an encrypted evidence store for safety analysis (STPA, CAST),
governance (GRC), and supply-chain security. It is optional, and the default SQLCipher
backend needs `libsqlcipher-dev` on the host (see prerequisites above).

Create the store before starting the backend: the assurance modules register when the backend
starts.

```bash
# Create the encrypted database and store the key in the OS credential backend
uv run arch-assurance init

# Start the backend (§4), then verify the key, set the activation gate, and authorize it
uv run arch-backend --daemon
uv run arch-assurance unlock

# Save the recovery key offline (store it in a password manager)
uv run arch-assurance export-key
```

`unlock` reports what the running backend answered. When it answers that it is still locked, the
backend cannot read the key in its own environment — for example it was started without the
`ARCH_ASSURANCE_MASTER_PASSWORD` the command had — and `unlock` exits 1 and says so. Restart the
backend from an environment that can read the key and run `unlock` again.

**Example content for the bundled self-model.** The self-model ships an example analysis in
`.arch-repo/assurance-seed.json`. In the workspace the checkout ships, load it with:

```bash
uv run arch-assurance seed                  # the analysis that ships with the self-model
uv run arch-assurance seed --with-signals   # also its signal anchors (queries OSV; needs network)
```

A repository of your own ships no seed; its store starts empty and needs none.

Whether a *newly started* backend opens the store by itself is the `activation_policy` setting,
not something `unlock` decides. The shipped default is `manual`: a restarted process starts locked
and needs `arch-assurance unlock` again — which is right on a workstation, where a restart is a
human act. For an unattended deployment, where nobody is there to run it, switch to
`arch-assurance use-backend sqlcipher --activation-policy persistent` (what the container does).
The full backend matrix, credential storage per OS, WORM archives, and the CLI reference live in
[Assurance: storage & confidentiality](04-assurance/storage-and-confidentiality.md).

---

&nbsp;

## Deployment topology

The backend supports two deployment profiles. Both profiles share the same process and the
same configuration — what differs is the host environment and the number of concurrent callers.

### Single-architect (local)

One person runs the backend on their own workstation. The GUI and any MCP-connected agents
share a single backend process. This is the default and requires no additional configuration.

```
workstation ── arch-backend (port 8000) ── GUI (browser)
                                        └─ MCP agents (stdio bridges)
```

### Team-serving

The backend runs on a shared host (a team server, a container, a VM) and serves multiple
engineers and agents concurrently. The backend is designed to handle this without additional
configuration: reads from the assurance store are concurrent (each request gets its own
connection from a thread-local connection pool operating in WAL mode), while writes are
serialized through a single-writer queue so there are never concurrent mutations.

```
team server ── arch-backend ── GUI clients (browsers)
                            └─ MCP agents (many concurrent)
```

The backend has no authentication, so it listens on the loopback address unless told otherwise.
To serve a team, put it behind something that guards the address (a VPN, a firewall or an
authenticating reverse proxy) and opt in:

```bash
ARCH_ALLOWED_HOSTS=arch.internal:*,10.0.0.5:* \
  uv run arch-backend --host 0.0.0.0 --allow-remote-without-auth --daemon
```

`--allow-remote-without-auth`, or `backend.allow_remote_without_auth: true` in
`config/settings.yaml`, permits an address other than the loopback. `ARCH_ALLOWED_HOSTS` lists the
names clients use to reach it; a request addressed to any other name is refused with `421`, on the
GUI, REST and MCP alike. See [CLI & backend](reference/cli-and-backend.md#backend)
for the entry syntax, and [Docker Compose](reference/docker-compose.md#vpn-access--the-reverse-proxy)
for a container.

Point clients at the shared backend by setting `ARCH_MCP_BACKEND_URL` in the MCP server
config and opening `http://<host>:8000` in a browser. No per-client backend is needed.

What a remote client can reach is bounded:

- Every response carries a content security policy that allows scripts only from the application
  itself, never inline, and forbids framing, together with `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`.
- No location a client names is read, evaluated or written outside the repositories the backend
  serves. An MCP `repo_root` must be the engagement or enterprise repository, and an
  `enterprise_root` the enterprise one; symbolic links and `..` are resolved before the check.
- Authorizing the backend to open the assurance store is accepted only from the backend's own
  machine.

For assurance, one operator holds the encryption key and runs `arch-assurance unlock` on the
server. Set `storage.assurance.activation_policy: persistent` there so an unattended reboot
reopens the store instead of taking the capability down until someone is available to unlock it
— see [Activation](04-assurance/storage-and-confidentiality.md#activation). The
`max_classification` ceiling can be set lower than `TLP:RED` so
team members access analysis results without seeing the most sensitive records — see
[TLP ceiling](04-assurance/storage-and-confidentiality.md#tlp-ceiling-and-withheld-content).

---

*Next: [Architecture Modeling →](03-modeling/index.md)*
