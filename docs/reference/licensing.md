# Licensing

## The project's own license

Architectonic is published under the **MIT License** — see [`LICENSE`](../../LICENSE) at the
repository root. You may use, modify, and distribute it, including for commercial purposes and
integration into commercial products, subject only to preserving the copyright and permission
notice.

The SPDX identifier for the project is `MIT`. The license file rides in every artifact adopters
receive: the source tree, the Docker image (`/app/LICENSE`), and any published Python
wheel/sdist (`license-files`).

&nbsp;

## Third-party components

Architectonic bundles, links, or invokes third-party components, each under its own license. All
are compatible with MIT redistribution — the stack is permissive (MIT/BSD/Apache/ISC/PSF), with a
few weak-copyleft components used at arm's length or unmodified, and no strong-copyleft component
linked into the project's own code.

**This project distributes source and a build recipe — it conveys no third-party binaries.** The
Debian packages arrive via `apt-get` during `docker build`, the PlantUML jar from Maven Central via
`get-plantuml`, the Python libraries from PyPI. Those upstreams are the distributors and each
discharges its own source-availability duty, so no corresponding-source obligation arises here.

The authoritative, generated list is [`THIRD-PARTY-NOTICES.md`](../../THIRD-PARTY-NOTICES.md) at the
repository root (shipped in the wheel and in a built image). It is a **disclosure inventory**: what
a build assembles, under what terms, why none of it reaches Architectonic's own code — and a closing
section on what changes if *you* publish a built image. Reference copies of the copyleft license
texts are in [`licenses/texts/`](../../licenses/texts/) and are copied into the image for that
reader's benefit.

### Notable components

- **PlantUML** (diagram rendering) is GPLv3. The jar is not in this repository — `get-plantuml`
  downloads the unmodified official build from Maven Central — and it is invoked as a **separate
  process** (`java -jar`). Two independent reasons it does not reach project code: running a
  separate process forms no combined work, and §5's aggregate clause covers an image holding the
  jar beside MIT code.
- **OpenJDK** (the default JRE) and **git** are GPL-2.0, apt-fetched from Debian at build time. The
  Classpath Exception is about linking against the class libraries, which nothing here does;
  running a program on a JRE needs no permission at all (GPLv2 §0).
- **Graphviz** (EPL-1.0, per-Contribution weak copyleft) and the **cvss** library (LGPLv3+, an
  ordinary runtime import from PyPI, replaceable with `pip install`) are weak-copyleft, both used
  unmodified and neither vendored.

### If you publish a built image

You then convey those binaries, and that is **ordinary, low-risk practice** for this image: every
copyleft component in it is an unmodified upstream package whose exact version is identifiable and
whose source is permanently retrievable from Debian (`apt-get source`, snapshot.debian.org) or Maven
Central. It stops being ordinary if you **modify** one of them, or **compile against** one instead
of invoking it — then the corresponding source is yours to supply. Leave them unmodified, pin the
base image by digest, and keep the notices file in the image. The notices file's closing section
spells this out per license family.

### Bringing your own Java runtime

PlantUML needs a Java runtime, and which one is entirely the deployer's choice. The
executable is resolved in this order:

1. **`ARCH_JAVA`** — an explicit path to a `java` executable (environment variable);
2. **`JAVA_HOME`** — resolved as `$JAVA_HOME/bin/java`;
3. **`java`** on `PATH`.

So a deployment can substitute any compatible JRE — a distribution package, a
vendor build, or a minimized custom runtime — without changing configuration files
or the shipped default.

&nbsp;

## How the inventory stays honest

Per-ecosystem inventories live under [`licenses/`](../../licenses/):

- `python.json` and `npm.json` are **generated** by
  `tools/licensing/check_licenses.py --ecosystem python|npm --write` from the actually-installed
  dependency metadata, and each entry is classified against an allow/deny policy.
- `native.json` records the non-package components (bundled jar, system libraries the
  runtime links or invokes) that no package manager can enumerate.
- `THIRD-PARTY-NOTICES.md` is **generated from all three** by `tools/licensing/generate_notices.py`.

CI enforces this on every push (the `licenses` job):

```bash
uv run python tools/licensing/check_licenses.py --ecosystem python --check   # drift + denied/unknown/unacknowledged
uv run python tools/licensing/check_licenses.py --ecosystem npm --check
uv run python tools/licensing/generate_notices.py --check                    # notices stale vs. inventories,
                                                                             # and every cited license text present
```

`--check` fails on any inventory drift, and on any component whose license is not
affirmatively classified as compatible — so a new dependency with a problematic or
unrecognized license cannot land silently.

**After changing dependencies** (Python or npm), regenerate and commit:

```bash
uv run python tools/licensing/check_licenses.py --ecosystem python --write
uv run python tools/licensing/check_licenses.py --ecosystem npm --write
uv run python tools/licensing/generate_notices.py --write
```

A change to a bundled or system-level component is recorded by editing
`licenses/native.json` directly, then regenerating the notices.

&nbsp;

## Dependency vulnerability posture

License compliance and vulnerability exposure are tracked separately. Dependency CVEs
are monitored with OSV-based scanning, and the project dogfoods its own
security-signals capability: SBOMs of the backend and the GUI are ingested as signal
snapshots against the corresponding self-model components (see
[Security signals](../04-assurance/security-signals.md)). This records the posture at a
point in time — it is not a warranty; consumers with their own compliance obligations
should scan the versions they actually deploy.

&nbsp;

*Not legal advice.* The classifications record each component's compatibility with MIT
redistribution as assessed by this project; where your own obligations require it,
verify independently against the versions you deploy.

---

*See also: [Installation & Setup](../02-installation.md) · [Docker Compose deployment](docker-compose.md)*
