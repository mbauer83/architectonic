"""One PlantUML JVM kept running in pipe mode, so the JVM start is paid once rather than per diagram.

PlantUML's `-pipe` reads diagrams from stdin for as long as stdin stays open, draws each one when its
`@end` line arrives, and writes the picture to stdout followed by the delimiter it was given. Measured
over the committed diagrams: byte-identical pictures to a run per file, at a median of 23 ms an SVG
instead of 840 ms (the spike note in the planning directory has the numbers).

The protocol has three hazards, and this class is where each is answered:

* **Framing.** A request is exactly one `@start…@end` block. Anything else — no block, two, a block
  with no end — would leave text in PlantUML's buffer that becomes part of the *next* diagram, so it
  never reaches a live process (`plantuml_runner` draws it in a run of its own instead).
* **Attribution.** PlantUML writes a refusal to stderr, autoflushed, *before* it writes the delimiter
  to stdout. Draining stderr after the delimiter therefore collects exactly what this diagram said.
* **A process that stops answering.** There is no exit code per diagram to wait on, so a render has a
  deadline on its delimiter; past it the JVM is killed and the next render starts a fresh one. One that
  died mid-render is replaced and the render tried once more, because the cause was the process.

Serialised by a lock: one diagram in flight per process, so outputs cannot interleave. A JVM left idle
for `idle_seconds` is stopped, and the next draw starts another: a warm one holds a few hundred MB, and
a backend nobody is drawing with has no use for it.
"""

from __future__ import annotations

import contextlib
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import IO

from src.application.plantuml_drawing import Drawing, Drawn, NotDrawn, WhyNotDrawn

#: A diagram every PlantUML draws without GraphViz: what a new process is asked first, so the JVM start
#: and its warm-up are charged to the process, not to the first caller's render budget.
_WARM_UP = "@startuml\nA -> A\n@enduml\n"

#: How long a new process may take to start and draw the warm-up. Generous: it is paid once, and a
#: saturated machine (a test run on every core) is where a JVM start is slowest.
START_SECONDS = 120.0

#: How long a process asked to stop may take to exit on its own before it is killed.
_STOP_GRACE_SECONDS = 1.0

#: How often a wait for stdout also empties stderr, so a long error stream cannot fill its pipe and
#: stall PlantUML before it writes the delimiter.
_STDERR_DRAIN_SECONDS = 0.05


@dataclass(frozen=True)
class _Answer:
    picture: bytes
    diagnostics: str


@dataclass(frozen=True)
class _Lost:
    why: WhyNotDrawn
    detail: str


def _read_into(descriptor: int, chunks: queue.Queue[bytes]) -> None:
    """Move everything read from *descriptor* into *chunks*; an empty chunk says the stream ended."""
    with contextlib.suppress(OSError):
        while chunk := os.read(descriptor, 1 << 16):
            chunks.put(chunk)
    chunks.put(b"")


class _Running:
    """A started JVM, its stdout reader and the directory it runs in."""

    def __init__(self, command: Sequence[str], env: Mapping[str, str] | None, delimiter: bytes) -> None:
        self._scratch = tempfile.TemporaryDirectory(prefix="arch-plantuml-")
        self._delimiter = delimiter
        self._stopped = threading.Lock()
        try:
            self.process = subprocess.Popen(  # noqa: S603 - the command is the owner's, built from fixed parts
                [*command, "-pipe", "-pipedelimitor", delimiter.decode("ascii")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self._scratch.name, env=None if env is None else dict(env),
            )
        except OSError:
            self._scratch.cleanup()
            raise
        stdin, stdout, stderr = self.process.stdin, self.process.stdout, self.process.stderr
        if stdin is None or stdout is None or stderr is None:  # pragma: no cover - all three are PIPE
            raise OSError("PlantUML was started without its pipes")
        self._stdin: IO[bytes] = stdin
        self._streams: tuple[IO[bytes], ...] = (stdin, stdout, stderr)
        self._stderr = stderr.fileno()
        os.set_blocking(self._stderr, False)
        self._chunks: queue.Queue[bytes] = queue.Queue()
        self._reader = threading.Thread(target=_read_into, args=(stdout.fileno(), self._chunks), daemon=True)
        self._reader.start()

    def exchange(self, block: str, deadline: float) -> _Answer | _Lost:
        """Send one block, and read its picture and what it said until *deadline*."""
        self._drain_stderr()  # anything left belongs to no diagram
        try:
            self._stdin.write(block.encode("utf-8"))
            self._stdin.flush()
        except (OSError, ValueError) as exc:
            return _Lost(WhyNotDrawn.STOPPED, str(exc))
        received = bytearray()
        diagnostics = bytearray()
        while (end := self._framed(received)) is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _Lost(WhyNotDrawn.TIMED_OUT, "")
            try:
                chunk = self._chunks.get(timeout=min(remaining, _STDERR_DRAIN_SECONDS))
            except queue.Empty:
                diagnostics += self._drain_stderr()
                continue
            if not chunk:
                said = (diagnostics + self._drain_stderr()).decode(errors="replace")
                return _Lost(WhyNotDrawn.STOPPED, said.strip()[:300])
            received += chunk
        diagnostics += self._drain_stderr()
        return _Answer(bytes(received[:end]), diagnostics.decode("utf-8", errors="replace"))

    def _framed(self, received: bytearray) -> int | None:
        """Where the picture ends, once its delimiter and the line end after it have arrived."""
        at = received.find(self._delimiter)
        if at < 0 or received.find(b"\n", at + len(self._delimiter)) < 0:
            return None
        return at

    def _drain_stderr(self) -> bytes:
        drained = bytearray()
        with contextlib.suppress(BlockingIOError, OSError, ValueError):
            while chunk := os.read(self._stderr, 1 << 16):
                drained += chunk
        return bytes(drained)

    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self, grace: float) -> None:
        """Close stdin, which ends a pipe-mode PlantUML; kill it if it has not exited within *grace*.

        Idempotent: a draw that saw the process die and a shutdown can both get here.
        """
        if not self._stopped.acquire(blocking=False):
            return
        with contextlib.suppress(OSError, ValueError):
            self._stdin.close()
        try:
            self.process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        # The reader sees end-of-file once the JVM is gone. Its descriptor is closed only after it has:
        # closed under a reader still blocked in it, the number could be reused and read from.
        self._reader.join(timeout=_STOP_GRACE_SECONDS)
        stdin, stdout, stderr = self._streams
        for stream in (stdin, stderr) if self._reader.is_alive() else (stdin, stdout, stderr):
            with contextlib.suppress(OSError, ValueError):
                stream.close()
        self._scratch.cleanup()


class PlantUmlProcess:
    """One long-lived PlantUML started lazily from *command*, restarted when it stops answering."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        start_seconds: float = START_SECONDS,
        idle_seconds: float | None = None,
    ) -> None:
        self._command = tuple(command)
        self._env = env
        self._start_seconds = start_seconds
        self._idle_seconds = idle_seconds
        self._idle_stop: threading.Timer | None = None
        #: One diagram in flight at a time.
        self._drawing = threading.Lock()
        #: Guards which JVM is current — separately, so `stop` never waits behind a draw.
        self._swapping = threading.Lock()
        self._running: _Running | None = None
        #: How many times `stop` was asked: a draw a stop cut short is not retried.
        self._stops = 0

    @property
    def pid(self) -> int | None:
        """The running JVM's process id, or None while none runs."""
        running = self._running
        return running.process.pid if running is not None and running.alive() else None

    def draw(self, block: str, *, timeout: float) -> Drawing:
        """The picture of *block* — exactly one `@start…@end` block — within *timeout* seconds.

        A process that died while drawing is replaced and the block tried once more — unless it was
        `stop` that ended it. A block still unanswered at its deadline kills the process, and the next
        draw starts a new one.
        """
        with self._drawing:
            stops = self._stops
            outcome = self._exchange(block, timeout)
            if isinstance(outcome, _Lost) and outcome.why is WhyNotDrawn.STOPPED and self._stops == stops:
                outcome = self._exchange(block, timeout)
        self._stop_when_idle()
        match outcome:
            case _Answer(picture=picture, diagnostics=diagnostics):
                return Drawn((picture,), diagnostics)
            case _Lost(why=WhyNotDrawn.TIMED_OUT, detail=""):
                return NotDrawn(WhyNotDrawn.TIMED_OUT, f"no picture within {timeout:g} s; the process was stopped")
            case _Lost(why=why, detail=detail):
                return NotDrawn(why, detail)

    def stop(self, grace: float = _STOP_GRACE_SECONDS) -> None:
        """Stop the JVM, if one runs, without waiting for a draw in flight — that draw fails, and is not
        retried. The next draw starts a new JVM."""
        with self._swapping:
            running, self._running = self._running, None
            self._stops += 1
            if self._idle_stop is not None:
                self._idle_stop.cancel()
        if running is not None:
            running.stop(grace)

    def _stop_when_idle(self) -> None:
        """Stop the current JVM once nothing has been drawn on it for `idle_seconds` — re-armed by every draw."""
        if self._idle_seconds is None:
            return
        with self._swapping:
            if self._idle_stop is not None:
                self._idle_stop.cancel()
            if (running := self._running) is None:
                return
            self._idle_stop = threading.Timer(self._idle_seconds, self._stop_if_still_idle, args=(running,))
            self._idle_stop.daemon = True
            self._idle_stop.start()

    def _stop_if_still_idle(self, running: _Running) -> None:
        # A draw in flight re-arms the timer when it finishes, so this one has nothing to stop.
        if not self._drawing.acquire(blocking=False):
            return
        try:
            with self._swapping:
                if self._running is not running:
                    return
                self._running = None
            running.stop(_STOP_GRACE_SECONDS)
        finally:
            self._drawing.release()

    def _exchange(self, block: str, timeout: float) -> _Answer | _Lost:
        running = self._started()
        if isinstance(running, _Lost):
            return running
        outcome = running.exchange(block, time.monotonic() + timeout)
        if isinstance(outcome, _Lost):
            self._discard(running)
        return outcome

    def _started(self) -> _Running | _Lost:
        current = self._running
        if current is not None and current.alive():
            return current
        if current is not None:
            self._discard(current)
        try:
            running = _Running(self._command, self._env, f"ARCH-PLANTUML-{secrets.token_hex(16)}".encode("ascii"))
        except OSError as exc:
            return _Lost(WhyNotDrawn.NO_JAVA, str(exc))
        with self._swapping:
            self._running = running
        match running.exchange(_WARM_UP, time.monotonic() + self._start_seconds):
            case _Answer():
                return running
            case _Lost(why=WhyNotDrawn.TIMED_OUT):
                self._discard(running)
                return _Lost(WhyNotDrawn.TIMED_OUT, f"PlantUML did not start within {self._start_seconds:g} s")
            case _Lost() as lost:
                self._discard(running)
                return lost

    def _discard(self, running: _Running) -> None:
        """Stop *running* now, and forget it if it is still the current JVM."""
        with self._swapping:
            if self._running is running:
                self._running = None
        running.stop(0.0)
