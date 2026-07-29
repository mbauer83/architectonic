# Installation & Setup

> Full setup, per operating system. For the five-minute path, see the
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
| Python | 3.13 | All server and CLI components |
| `uv` | any recent | Python environment and script runner |
| Java | 11 | PlantUML diagram rendering and verification |
| Graphviz | 2.49.0 | Diagram layout engine |
| Node.js | 20 | Frontend development only (not needed to run) |
| npm | 9 | Frontend development only |
| SQLCipher (system lib) | 4 | Assurance store (optional) |

---

&nbsp;

## Per-environment prerequisites

### macOS

```bash
# Core
brew install python@3.13 openjdk graphviz
curl -LsSf https://astral.sh/uv/install.sh | sh

# Frontend development (optional)
brew install node

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
sudo apt-get install -y python3.13 python3.13-dev default-jre graphviz curl

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Frontend development (optional) — use nvm or NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
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

&nbsp;

## 1. Install Python dependencies

```bash
# Core runtime
uv sync                           # core dependencies
uv sync --group dev               # + pytest, ruff, zuban  (alias: --dev)
uv sync --group gui               # + FastAPI / uvicorn for the GUI server
uv sync --group dev --group gui   # full local developer setup

# All dependency groups (dev tooling etc.). The assurance-store dependencies are part
# of the CORE dependencies (the host still needs libsqlcipher-dev for the store itself)
uv sync --all-groups

# Cloud archive backends (optional — pick what you need)
uv sync --extra s3-archive        # + boto3 for S3 Object Lock archive
uv sync --extra azure-archive     # + azure-storage-blob + azure-identity for Azure archive
uv sync --extra cloud-archive     # both S3 and Azure
```

> Use `uv sync`, not `pip install`. The `zuban` type checker ships in the `dev`
> dependency group (`uv sync --group dev`, included in `--all-groups`).

> **Running the project's commands.** `uv sync` installs this project's entry points
> (`arch-backend`, `arch-init`, `get-plantuml`, `arch-assurance`, …) into `.venv/`, which is not
> on your `PATH`. Every command below is therefore written as `uv run <command>`, which needs no
> activation and always resolves the project's own environment. If you prefer the bare names,
> activate the environment once per shell — `source .venv/bin/activate` (`.venv\Scripts\activate`
> on Windows) — and drop the `uv run` prefix.

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

An `arch-workspace.yaml` at the workspace root declares the two repositories. The simplest
form keeps a single explicit engagement:

```yaml
engagement:
  local: engagements/ENG-ARCH-REPO/architecture-repository
  # or git: { url: "https://...", branch: main, path: .arch/repos/engagement }

enterprise:
  local: enterprise-repository
  # or git: { url: "https://...", branch: main, path: .arch/repos/enterprise }
```

Then resolve and validate it:

```bash
uv run arch-init                      # reads arch-workspace.yaml, writes .arch/init-state.yaml

# If a configured git repo exists locally but is still empty / uninitialised
uv run arch-init --initialize-engagement-repo-if-empty
uv run arch-init --initialize-enterprise-repo-if-empty
```

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

See [Authoring guidance](05-extensibility/guidance.md) for the format and layering.

&nbsp;

## 4. Start the backend

`arch-backend` serves the REST API and the MCP endpoints. It also serves the GUI at `/` —
but **only if the SPA has been built** into `tools/gui/dist/` (see
[§6](#6-build-and-serve-the-gui)). Without that build, `/` returns nothing and you use the
APIs or the Vite dev server. The backend never builds or runs the frontend itself.

```bash
# Backend: REST API at :8000, MCP at :8000/mcp/{read,write}; GUI at / if built (§6)
uv run arch-backend --daemon

# Inspect / stop / restart
uv run arch-backend --status
uv run arch-backend --stop
uv run arch-backend --restart --daemon
```

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

**Serve the GUI from the backend (production / normal use).** Build once; the backend then
serves the result at `/`:

```bash
cd tools/gui
npm install
npm run build          # → tools/gui/dist/  (served by arch-backend at /)
cd ../..
```

Re-run `npm run build` after pulling frontend changes. The Docker image performs this build
automatically, so containerised deployments need no manual step.

**Develop with hot-reload (frontend work).** Run the Vite dev server instead of building; it
proxies API calls to the backend on :8000:

```bash
cd tools/gui
npm install
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

```bash
# Create the encrypted database and store the key in the OS credential backend
uv run arch-assurance init

# Verify the key, set the activation gate, and authorize the running backend
uv run arch-assurance unlock

# Save the recovery key offline (store it in a password manager)
uv run arch-assurance export-key

# Optional: seed the store with the bundled example content, including signal
# anchors for the self-model (a working store to explore before authoring)
uv run arch-assurance seed --with-signals
```

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

Point clients at the shared backend by setting `ARCH_MCP_BACKEND_URL` in the MCP server
config and opening `http://<host>:8000` in a browser. No per-client backend is needed.

For assurance, one operator holds the encryption key and runs `arch-assurance unlock` on the
server. Set `storage.assurance.activation_policy: persistent` there so an unattended reboot
reopens the store instead of taking the capability down until someone is available to unlock it
— see [Activation](04-assurance/storage-and-confidentiality.md#activation). The
`max_classification` ceiling can be set lower than `TLP:RED` so
team members access analysis results without seeing the most sensitive records — see
[TLP ceiling](04-assurance/storage-and-confidentiality.md#tlp-ceiling-and-withheld-content).

---

*Next: [Architecture Modeling →](03-modeling/index.md)*
