"""The one place this codebase runs PlantUML: every render, every syntax check, the doctor's version.

Before this module, four call sites each started a JVM per diagram — about 0.8 s of every render was
the JVM starting, and the tests serialised every one of them across workers with a file lock to keep
twenty cold starts from overrunning their budget. Now a diagram goes to a long-lived PlantUML in pipe
mode (`plantuml_process`), one per *launch*: the JVM, jar, GraphViz and arguments that decide the
picture. A process per launch, not one shared, because PlantUML fixes its output format and settings
when it starts; and one per launch, not a pool, because a warm render takes tens of milliseconds and
each JVM holds a few hundred MB once warm.

**The sandbox is stated here and nowhere else**, because this is the only module that assembles a
command: `-Djava.awt.headless=true` and `PLANTUML_SECURITY_PROFILE` on every run, whatever the
caller adds. `tests/architecture/test_one_module_runs_plantuml.py` refuses a second module that runs
the jar.

A source that is not exactly one `@start…@end` block is drawn by a PlantUML of its own, started and
ended for it, because in a shared process its stray text would become part of the next diagram.
"""

from __future__ import annotations

import atexit
import os
import secrets
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from src.application.plantuml_drawing import Drawing, Drawn, NotDrawn, PictureFormat, WhyNotDrawn
from src.application.verification.artifact_verifier_syntax import (
    find_graphviz_dot,
    find_plantuml_jar,
    resolve_java_executable,
)
from src.infrastructure.rendering.plantuml_process import PlantUmlProcess

#: PlantUML's own security profile for every run. SANDBOX refuses local file reads and URL fetches
#: by the preprocessor and by creole images, whatever spelling reaches it; the bundled standard
#: library (`!include <C4/…>`) still works, because it is read from the jar. The product expands its
#: own managed include fragments into a body before PlantUML sees it, so nothing it renders needs
#: more than this. The body policy (`puml_directive_policy`) refuses early and says why; this is what
#: holds when a spelling gets past it.
PLANTUML_SECURITY_PROFILE = "SANDBOX"

#: How a JVM that lives for the whole process is run. With the default collector (G1, a heap of up to a
#: quarter of the machine) a pipe-mode PlantUML grew to ~500 MB resident over 100 renders of this
#: project's diagrams; with the serial collector, ~290 MB for SVG and ~430 MB for PNG, at the same
#: speed. A JVM per render never lived long enough for this to matter. Not `TieredStopAtLevel=1`, which
#: halves memory again but doubled the PNG render time; and no heap ceiling, because a 16384-pixel PNG
#: legitimately needs the heap.
_LONG_LIVED_JVM = ("-XX:+UseSerialGC",)

#: How long a render may take, as before: a server answering one preview request.
RENDER_SECONDS = 60.0

#: How long a JVM may sit unused before it is stopped. Long enough that a person editing a diagram keeps
#: theirs warm between saves; short enough that a backend nobody draws with gives the memory back.
_IDLE_SECONDS = 300.0


def idle_seconds() -> float:
    """How long a JVM may sit unused. `ARCH_PLANTUML_IDLE_SECONDS` overrides it — so it can be re-measured
    without a release, and so a test run of many workers, each with its own JVMs, can give memory back
    sooner than an interactive backend should."""
    override = os.environ.get("ARCH_PLANTUML_IDLE_SECONDS", "").strip()
    try:
        return max(1.0, float(override)) if override else _IDLE_SECONDS
    except ValueError:
        return _IDLE_SECONDS


def plantuml_command(jar: Path, *arguments: str, system_properties: tuple[str, ...] = ()) -> list[str]:
    """The command line for one PlantUML — the only way this codebase starts one.

    `system_properties` are further `-D` (or `-XX`) settings, placed before `-jar` as the JVM requires.
    """
    return [
        resolve_java_executable(),
        "-Djava.awt.headless=true",
        f"-DPLANTUML_SECURITY_PROFILE={PLANTUML_SECURITY_PROFILE}",
        *system_properties,
        "-jar",
        str(jar),
        *arguments,
    ]


def render_settings(fmt: PictureFormat) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The PlantUML arguments and JVM settings a render in *fmt* is drawn with."""
    from src.config.settings import plantuml_limit_size, render_dpi  # noqa: PLC0415

    return (
        (f"-t{fmt}", *([f"-Sdpi={render_dpi()}"] if fmt == "png" else [])),
        (f"-DPLANTUML_LIMIT_SIZE={plantuml_limit_size()}",),
    )


#: What the syntax check draws with: SVG, and only the sandbox — as it always has.
_CHECK_SETTINGS: tuple[tuple[str, ...], tuple[str, ...]] = (("-tsvg",), ())


@dataclass(frozen=True)
class PlantUmlLaunch:
    """Everything that decides what a PlantUML process draws, and so which process draws it."""

    jar: Path
    java: str
    dot: Path | None
    arguments: tuple[str, ...]
    system_properties: tuple[str, ...]

    def command(self) -> list[str]:
        return plantuml_command(
            self.jar, *self.arguments, system_properties=(*_LONG_LIVED_JVM, *self.system_properties),
        )

    def environment(self) -> dict[str, str] | None:
        return None if self.dot is None else {**os.environ, "GRAPHVIZ_DOT": str(self.dot)}


def single_block(source: str) -> str | None:
    """*source*'s one diagram as a live pipe-mode PlantUML can be given it, or None where it cannot.

    Exactly one `@start` line, at the start of its line, and an `@end` line after it: anything else is
    left for a PlantUML of its own to read as it reads a file. Text around the block is dropped, as
    PlantUML drops it.
    """
    lines = source.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith("@start")]
    if len(starts) != 1 or not lines[starts[0]].startswith("@start"):
        return None
    end = next((index for index in range(starts[0] + 1, len(lines)) if lines[index].startswith("@end")), None)
    if end is None:
        return None
    block = "".join(lines[starts[0] : end + 1])
    return block if block.endswith("\n") else f"{block}\n"


def _draw_once(launch: PlantUmlLaunch, source: str, timeout: float) -> Drawing:
    """*source* drawn by a PlantUML started for it alone, which reads it to the end as it reads a file."""
    delimiter = f"ARCH-PLANTUML-{secrets.token_hex(16)}"
    try:
        finished = subprocess.run(  # noqa: S603 - the command is built from fixed parts above
            [*launch.command(), "-pipe", "-pipedelimitor", delimiter],
            input=source.encode("utf-8"), capture_output=True, timeout=timeout, env=launch.environment(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return NotDrawn(WhyNotDrawn.TIMED_OUT, f"no picture within {timeout:g} s; the process was stopped")
    except OSError as exc:
        return NotDrawn(WhyNotDrawn.NO_JAVA, str(exc))
    framed = finished.stdout.split(delimiter.encode("ascii"))
    pictures = tuple(part.removeprefix(b"\r\n").removeprefix(b"\n") for part in framed[:-1])
    return Drawn(pictures, finished.stderr.decode("utf-8", errors="replace"))


class PlantUmlRunner:
    """PlantUML for this process: one long-lived JVM per launch, started on first use."""

    def __init__(self) -> None:
        self._processes: dict[PlantUmlLaunch, PlantUmlProcess] = {}
        self._lock = threading.Lock()

    def draw(self, source: str, fmt: PictureFormat, *, timeout: float = RENDER_SECONDS) -> Drawing:
        """What PlantUML draws of a prepared *source* in *fmt*, with the render settings."""
        return self._drawn(source, render_settings(fmt), timeout)

    def draw_for_check(self, source: str, *, timeout: float) -> Drawing:
        """What PlantUML draws of *source* for the syntax check: SVG, with the sandbox and nothing else."""
        return self._drawn(source, _CHECK_SETTINGS, timeout)

    def process_ids(self) -> tuple[int, ...]:
        """The JVMs running now. For tests, and for asking what this process holds."""
        with self._lock:
            processes = tuple(self._processes.values())
        return tuple(pid for process in processes if (pid := process.pid) is not None)

    def stop(self) -> None:
        """Stop every JVM. A later draw starts its own again."""
        with self._lock:
            processes, self._processes = tuple(self._processes.values()), {}
        for process in processes:
            process.stop()

    def _drawn(self, source: str, settings: tuple[tuple[str, ...], tuple[str, ...]], timeout: float) -> Drawing:
        jar = find_plantuml_jar()
        if jar is None:
            return NotDrawn(WhyNotDrawn.NO_PLANTUML)
        arguments, system_properties = settings
        launch = PlantUmlLaunch(
            jar.resolve(), resolve_java_executable(), find_graphviz_dot(), arguments, system_properties,
        )
        if (block := single_block(source)) is None:
            return _draw_once(launch, source, timeout)
        return self._process_for(launch).draw(block, timeout=timeout)

    def _process_for(self, launch: PlantUmlLaunch) -> PlantUmlProcess:
        with self._lock:
            if (process := self._processes.get(launch)) is None:
                process = self._processes[launch] = PlantUmlProcess(
                    launch.command(), env=launch.environment(), idle_seconds=idle_seconds(),
                )
            return process


def plantuml_version(jar: Path) -> tuple[int, str]:
    """What `-version` says of *jar*, and the exit status: for the doctor, which checks the toolchain."""
    finished = subprocess.run(  # noqa: S603 - the command is built from fixed parts above
        plantuml_command(jar, "-version"), capture_output=True, text=True, check=False,
    )
    return finished.returncode, (finished.stdout + finished.stderr).strip()


#: The process's PlantUML. Stopped on the way out — by the backend's teardown inside its budget, and
#: by `atexit` for every other process. A process killed outright leaves no JVM either: pipe-mode
#: PlantUML exits when its stdin closes, and a dead parent closes it.
PLANTUML = PlantUmlRunner()
atexit.register(PLANTUML.stop)
