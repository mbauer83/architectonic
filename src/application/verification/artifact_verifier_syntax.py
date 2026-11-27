import os
import re
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.application.plantuml_drawing import Drawn, NotDrawn, SyntaxDrawing, WhyNotDrawn
from src.application.plantuml_pictures import DRAWN, picture_key
from src.application.puml_directive_policy import find_unsafe_puml_directives
from src.application.verification._verifier_rules_rendered_picture import RenderedPictureChecks
from src.application.verification.artifact_verifier_types import Issue, Severity

#: Where the PlantUML jar may sit relative to the directory holding pyproject.toml, in
#: precedence order. The first entry is the canonical location: `get-plantuml`,
#: `get-diagram-runtime`, and the Docker image all provision it there. Anything that writes
#: or checks the jar reads this rather than restating a path of its own, so a provisioning
#: command and a lookup cannot disagree about where the jar lives.
PLANTUML_JAR_RELPATHS: tuple[str, ...] = ("plantuml.jar", "tools/plantuml.jar")


#: Every finding the PlantUML syntax check gives a diagram, the checks on the picture it draws
#: included. Declared so that what the check covers is a fact a reader can see;
#: `test_each_verifier_declares_its_rule_codes` holds it equal to the codes its modules emit.
RULE_CODES: frozenset[str] = frozenset({
    "E350", "E353", "W350", "W351", "W352", "W370", "W371", "W372", "W373", "W374", "W380", "W381", "W382",
    "W383", "W384", "W385", "W386",
})


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



def body_reaches_outside(path: Path, loc: str) -> Issue | None:
    """E353 when a diagram file references a file, URL or environment value, so it is never rendered.

    The syntax check renders the file, and a file can arrive through git without passing any write
    path, so this check is the only one a body written elsewhere is certain to meet.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    offenders = find_unsafe_puml_directives(text)
    if not offenders:
        return None
    return Issue(
        Severity.ERROR,
        "E353",
        f"The body references a file, URL or environment value and was not rendered: "
        f"{'; '.join(offenders[:3])}. A body may "
        "include only the bundled standard library and the managed fragments, and may embed images "
        "only as data:image/…;base64.",
        loc,
    )


#: How long PlantUML may take over one file's syntax check.
_CHECK_SECONDS = 30.0


@dataclass(frozen=True)
class _Diagram:
    """A diagram file as PlantUML reads it: from its first `@start` line on, and which line that is."""

    source: str
    first_line: int


def _diagram_in(path: Path) -> _Diagram | None:
    """The diagram in *path* — the frontmatter above it is read by nobody. None where it cannot be read
    or has no diagram in it."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    start = re.search(r"^[ \t]*@start", text, re.MULTILINE)
    if start is None:
        return None
    return _Diagram(text[start.start():], text.count("\n", 0, start.start()))


def _drawn_key(diagram: _Diagram, jar: Path) -> str | None:
    """What decides the picture the syntax check draws of a diagram (`plantuml_pictures`): the diagram as
    PlantUML reads it. Not where it is: a body that names a file is never kept, and one that reaches
    outside is refused before it is drawn (`body_reaches_outside`), so nothing in a kept body is read
    relative to the file."""
    return picture_key(
        diagram.source, "verify", "-tsvg", jar=jar, dot=find_graphviz_dot(), java=resolve_java_executable(),
    )


def check_puml_syntax(
    path: Path, loc: str, *, drawing: SyntaxDrawing, picture_checks: RenderedPictureChecks | None = None
) -> list[Issue]:
    """E350 where PlantUML refuses the body; where it draws it, what *picture_checks* say of the picture."""
    if (refused := body_reaches_outside(path, loc)) is not None:
        return [refused]
    if os.environ.get("ARCH_SKIP_PUML_SYNTAX"):
        return []
    jar = find_plantuml_jar()
    if jar is None:
        return [Issue(Severity.WARNING, "W350", "plantuml.jar not found; PUML syntax check skipped", loc)]
    diagram = _diagram_in(path)
    key = None if diagram is None else _drawn_key(diagram, jar)
    if (kept := DRAWN.recall(key)) is not None:
        return [] if picture_checks is None else picture_checks.check(kept.decode("utf-8"), loc)
    source = diagram.source if diagram is not None else _readable(path)
    match drawing.draw_for_check(source, timeout=_CHECK_SECONDS):
        case NotDrawn(why=WhyNotDrawn.NO_JAVA):
            return [Issue(Severity.WARNING, "W351", "java not found on PATH; PUML syntax check skipped", loc)]
        case NotDrawn(why=WhyNotDrawn.TIMED_OUT):
            return [Issue(Severity.WARNING, "W352", f"plantuml render timed out after {_CHECK_SECONDS:g} s", loc)]
        case NotDrawn() as failed:
            return [Issue(Severity.ERROR, "E350", f"PlantUML error: {failed.reason[:200]}", loc)]
        case Drawn(refusals=()) as drawn:
            if drawn.picture is None:
                return []
            DRAWN.keep(key, drawn.picture)
            return [] if picture_checks is None else picture_checks.check(drawn.picture.decode("utf-8"), loc)
        case Drawn(refusals=refusals):
            # Counted as PlantUML counts lines of a file, which is how the finding has always read.
            first_line = 0 if diagram is None else diagram.first_line
            return [
                Issue(Severity.ERROR, "E350", f"PlantUML: Error line {first_line + line + 1} in file: {path}", loc)
                for line in (refusal.line_from_start for refusal in refusals)
            ]


def _readable(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def check_puml_syntax_batch(
    paths: list[Path], *, drawing: SyntaxDrawing, picture_checks: RenderedPictureChecks | None = None
) -> dict[Path, list[Issue]]:
    """The syntax findings of every path, each file drawn on its own by the one PlantUML that draws them all.

    Each on its own, now that a drawing costs no JVM start: a run over many files used to share one JVM
    and then had to work out from its output which file a refusal belonged to.
    """
    return {
        path: check_puml_syntax(path, str(path), drawing=drawing, picture_checks=picture_checks) for path in paths
    }
