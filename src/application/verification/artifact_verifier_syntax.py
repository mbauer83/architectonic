import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from src.application.verification.artifact_verifier_types import Issue, Severity

#: Where the PlantUML jar may sit relative to the directory holding pyproject.toml, in
#: precedence order. The first entry is the canonical location: `get-plantuml`,
#: `get-diagram-runtime`, and the Docker image all provision it there. Anything that writes
#: or checks the jar reads this rather than restating a path of its own, so a provisioning
#: command and a lookup cannot disagree about where the jar lives.
PLANTUML_JAR_RELPATHS: tuple[str, ...] = ("plantuml.jar", "tools/plantuml.jar")


@lru_cache(maxsize=1)
def find_plantuml_jar() -> Path | None:
    candidate = Path(__file__).resolve()
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            for relpath in PLANTUML_JAR_RELPATHS:
                jar = candidate / relpath
                if jar.exists():
                    return jar
            return None
    return None


@lru_cache(maxsize=1)
def find_graphviz_dot() -> Path | None:
    env_dot = os.environ.get("GRAPHVIZ_DOT", "").strip()
    if env_dot:
        candidate = Path(env_dot)
        if candidate.exists():
            return candidate

    candidate = Path(__file__).resolve()
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            local_names = ("dot.exe", "dot") if os.name == "nt" else ("dot",)
            for name in local_names:
                bundled = candidate / "tools" / "graphviz" / "bin" / name
                if bundled.exists():
                    return bundled
            break

    which_dot = shutil.which("dot")
    return Path(which_dot) if which_dot else None


def resolve_java_executable() -> str:
    """Resolve the java binary used to run the bundled PlantUML jar.

    Honours, in priority order:
      1. the ``ARCH_JAVA`` environment variable (explicit executable path),
      2. ``JAVA_HOME`` (→ ``$JAVA_HOME/bin/java``),
      3. ``java`` on ``PATH`` (the bundled default JRE).

    The override (1) is consulted only when explicitly set, so the compatible
    bundled OpenJDK default is never silently replaced by an incompatible one.
    This mirrors the ``GRAPHVIZ_DOT`` escape hatch used by ``find_graphviz_dot``
    for the sibling diagram-runtime binary — an environment channel, so the
    application layer stays free of a configuration-module dependency.
    """
    explicit = os.environ.get("ARCH_JAVA", "").strip()
    if explicit:
        return str(Path(explicit).expanduser())
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        return str(Path(java_home) / "bin" / "java")
    return "java"


#: How many files a pass verifies at once, by default.
#:
#: One. Not a fraction of the machine, and emphatically not ``cpu + 4``, which is the
#: ``ThreadPoolExecutor`` default and is sized for work that *waits*. Rule evaluation never waits, and
#: the pool was measured making the pass slower on every axis at once. Interleaved, repeated runs
#: against the 880-file repository, wall clock and the backend's own CPU seconds:
#:
#: ===========  ==========  ==========  =====================================
#: workers      wall        backend     identity p95 during the pass
#: ===========  ==========  ==========  =====================================
#: 1             73 s         92 s       11.6 ms  (1.5x its idle value)
#: 2            161 s          —         14.7 ms
#: 4            314 s        408 s       18.6 ms  (2.7x)
#: 20           298 s        403 s       44.9 ms  (5.9x)
#: ===========  ==========  ==========  =====================================
#:
#: Four threads spent **4.4x the CPU** of one for the same 880 files — redundant work rather than
#: scheduling overhead. A profile put that pass in pure-Python YAML parsing (200,574 documents) and
#: path resolution (982,904 ``realpath`` calls), neither of which parallelises here.
#:
#: **Re-measured 2026-08-11, and the costs above are gone.** Same repository, same settings, PlantUML
#: syntax skipped: a full pass over 965 files parses **1,472** YAML documents and makes **3,392**
#: ``realpath`` calls, and takes **0.19 s**. Single acquisition (``acquire_snapshot``) removed the
#: re-reading, and `domain.yaml_documents.parse_yaml` moved the remaining parse onto libyaml.
#:
#: So the table records a real measurement of a state this code is no longer in, and it is kept
#: because it is what the default was chosen from. **The default stays 1 for a new reason:** there is
#: no longer a pass worth splitting. Sharing 0.19 s across threads cannot repay a pool, and the
#: interactive cost of trying is unchanged. Re-measure before changing this, not from either number
#: above.
_DEFAULT_PASS_WORKERS = 1


def resolve_worker_count() -> int:
    """How many files a pass verifies at once.

    ``ARCH_VERIFY_WORKERS`` overrides it, so the number can be re-measured without a release to change
    a constant. The per-file cost the table above describes has since come down by two orders of
    magnitude, which removed the reason to raise this rather than supplying one: a 0.19 s pass has
    nothing left to divide.
    """
    override = os.environ.get("ARCH_VERIFY_WORKERS", "").strip()
    if override.isdigit() and int(override) > 0:
        return min(32, int(override))
    return _DEFAULT_PASS_WORKERS



def check_puml_syntax(path: Path, loc: str) -> list[Issue]:
    if os.environ.get("ARCH_SKIP_PUML_SYNTAX"):
        return []
    result: list[Issue] = []
    jar = find_plantuml_jar()
    if jar is None:
        return [
            Issue(
                Severity.WARNING,
                "W350",
                "plantuml.jar not found; PUML syntax check skipped",
                loc,
            )
        ]

    java_exe = resolve_java_executable()
    env = os.environ.copy()
    dot = find_graphviz_dot()
    if dot is not None:
        env["GRAPHVIZ_DOT"] = str(dot)

    try:
        with tempfile.TemporaryDirectory() as tmp_out:
            proc = subprocess.run(
                [
                    java_exe,
                    "-Djava.awt.headless=true",
                    "-jar",
                    str(jar),
                    "-tsvg",
                    "-verbose",
                    "-o",
                    tmp_out,
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
    except FileNotFoundError:
        return [Issue(Severity.WARNING, "W351", "java not found on PATH; PUML syntax check skipped", loc)]
    except subprocess.TimeoutExpired:
        return [Issue(Severity.WARNING, "W352", "plantuml render timed out after 30 s", loc)]

    if proc.returncode == 0:
        return result

    combined = proc.stdout + proc.stderr
    error_lines = re.findall(r"^Error line \d+ in file:.*$", combined, re.MULTILINE)
    syntax_lines = re.findall(r"Syntax Error\?.*", combined)
    reported = error_lines or syntax_lines

    if reported:
        for line in reported:
            result.append(Issue(Severity.ERROR, "E350", f"PlantUML: {line.strip()}", loc))
        return result

    signal_lines = [
        ln.strip()
        for ln in combined.splitlines()
        if ln.strip()
        and "IOException" not in ln
        and "Cannot run program" not in ln
        and "Caused by" not in ln
        and "at java." not in ln
        and "at net." not in ln
        and ln.strip() not in ("Some diagram description contains errors",)
    ]
    msg = signal_lines[0] if signal_lines else f"exit {proc.returncode}"
    return [Issue(Severity.ERROR, "E350", f"PlantUML error (exit {proc.returncode}): {msg[:200]}", loc)]


def check_puml_syntax_batch(paths: list[Path], *, chunk_size: int = 120) -> dict[Path, list[Issue]]:
    issues_by_path: dict[Path, list[Issue]] = {p: [] for p in paths}
    if not paths or os.environ.get("ARCH_SKIP_PUML_SYNTAX"):
        return issues_by_path

    jar = find_plantuml_jar()
    if jar is None:
        for path in paths:
            issues_by_path[path].append(
                Issue(
                    Severity.WARNING,
                    "W350",
                    "plantuml.jar not found; PUML syntax check skipped",
                    str(path),
                )
            )
        return issues_by_path

    java_exe = resolve_java_executable()
    env = os.environ.copy()
    dot = find_graphviz_dot()
    if dot is not None:
        env["GRAPHVIZ_DOT"] = str(dot)

    for i in range(0, len(paths), chunk_size):
        path_chunk = paths[i : i + chunk_size]
        try:
            with tempfile.TemporaryDirectory() as tmp_out:
                proc = subprocess.run(
                    [
                        java_exe,
                        "-Djava.awt.headless=true",
                        "-jar",
                        str(jar),
                        "-tsvg",
                        "-verbose",
                        "-o",
                        tmp_out,
                        *[str(p) for p in path_chunk],
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=env,
                )
        except FileNotFoundError:
            for path in path_chunk:
                issues_by_path[path].append(
                    Issue(
                        Severity.WARNING,
                        "W351",
                        "java not found on PATH; PUML syntax check skipped",
                        str(path),
                    )
                )
            continue
        except subprocess.TimeoutExpired:
            for path in path_chunk:
                issues_by_path[path].append(
                    Issue(
                        Severity.WARNING,
                        "W352",
                        "plantuml render timed out after 120 s",
                        str(path),
                    )
                )
            continue

        if proc.returncode == 0:
            continue

        combined = proc.stdout + proc.stderr
        file_error_matches = re.findall(r"^Error line \d+ in file: (.*)$", combined, re.MULTILINE)
        attributed = False
        if file_error_matches:
            for matched_path in file_error_matches:
                candidate = Path(matched_path.strip())
                issue = Issue(
                    Severity.ERROR,
                    "E350",
                    f"PlantUML: Error line in file: {candidate}",
                    str(candidate),
                )
                if candidate in issues_by_path:
                    issues_by_path[candidate].append(issue)
                    attributed = True
                else:
                    resolved = candidate.resolve()
                    if resolved in issues_by_path:
                        issues_by_path[resolved].append(issue)
                        attributed = True

        syntax_lines = re.findall(r"Syntax Error\?.*", combined)
        if syntax_lines:
            fallback = syntax_lines[0].strip()
            for path in path_chunk:
                if not issues_by_path[path]:
                    issues_by_path[path].append(
                        Issue(
                            Severity.ERROR,
                            "E350",
                            f"PlantUML: {fallback}",
                            str(path),
                        )
                    )
            attributed = True

        if attributed:
            continue

        # Batch output was non-zero but could not be attributed to specific files.
        # Fall back to per-file checks to avoid false positives across the chunk.
        for path in path_chunk:
            single_issues = check_puml_syntax(path, str(path))
            issues_by_path[path].extend(single_issues)

    return issues_by_path
