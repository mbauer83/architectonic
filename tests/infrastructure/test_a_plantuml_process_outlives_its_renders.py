"""A long-lived PlantUML answers render after render, and is replaced when it stops answering.

Driven against a stand-in that speaks PlantUML's pipe protocol — read a block to its `@end` line, write
a picture and the delimiter — so a process that hangs, dies mid-render or refuses a body is something
a test can ask for. The real PlantUML is driven in `tests/rendering/test_one_plantuml_draws_every_render.py`.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from src.application.plantuml_drawing import Drawn, NotDrawn, WhyNotDrawn
from src.infrastructure.rendering.plantuml_process import PlantUmlProcess
from src.infrastructure.rendering.plantuml_runner import single_block

_STAND_IN = """
import os, sys, time
delimiter = sys.argv[sys.argv.index("-pipedelimitor") + 1]
marker = sys.argv[1]
answered = 0
block = []
for line in sys.stdin:
    block.append(line)
    if not line.startswith("@end"):
        continue
    text, block = "".join(block), []
    if "hang" in text:
        time.sleep(600)
    if "die-once" in text and not os.path.exists(marker):
        open(marker, "w").close()
        os._exit(3)
    if "die-always" in text:
        os._exit(3)
    if "refuse" in text:
        sys.stderr.write("ERROR\\n1\\nSyntax Error? (stand-in)\\n")
        sys.stderr.flush()
    answered += 1
    sys.stdout.write(f"<svg>{os.getpid()}:{answered}</svg>{delimiter}\\n")
    sys.stdout.flush()
"""


def _block(word: str) -> str:
    return f"@startuml\n{word}\n@enduml\n"


@pytest.fixture
def stand_in(tmp_path: Path):
    script = tmp_path / "stand_in.py"
    script.write_text(_STAND_IN, encoding="utf-8")
    process = PlantUmlProcess([sys.executable, str(script), str(tmp_path / "died-once")], start_seconds=30)
    yield process
    process.stop()


def _picture(drawing: Drawn | NotDrawn) -> str:
    assert isinstance(drawing, Drawn), drawing
    assert drawing.picture is not None
    return drawing.picture.decode()


def _gone(pid: int) -> bool:
    """Whether *pid* has exited — reaped, or a zombie its parent has not reaped yet."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (ProcessLookupError, FileNotFoundError):
            return True
        if state == "Z":
            return True
        time.sleep(0.05)
    return False


class TestOneProcess:
    def test_is_started_on_first_use_and_shared_by_every_render(self, stand_in: PlantUmlProcess) -> None:
        assert stand_in.pid is None

        first = _picture(stand_in.draw(_block("one"), timeout=10))
        second = _picture(stand_in.draw(_block("two"), timeout=10))

        pid = stand_in.pid
        # The warm-up was the first answer; each render is a further answer from the same process.
        assert (first, second) == (f"<svg>{pid}:2</svg>", f"<svg>{pid}:3</svg>")

    def test_what_a_refused_body_says_belongs_to_that_body_alone(self, stand_in: PlantUmlProcess) -> None:
        refused = stand_in.draw(_block("refuse"), timeout=10)
        accepted = stand_in.draw(_block("fine"), timeout=10)

        assert isinstance(refused, Drawn) and [r.message for r in refused.refusals] == ["Syntax Error? (stand-in)"]
        assert isinstance(accepted, Drawn) and accepted.refusals == () and accepted.diagnostics == ""

    def test_concurrent_renders_do_not_interleave(self, stand_in: PlantUmlProcess) -> None:
        pictures: list[str] = []
        threads = [
            threading.Thread(target=lambda n=n: pictures.append(_picture(stand_in.draw(_block(f"n{n}"), timeout=10))))
            for n in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        pid = stand_in.pid
        assert sorted(pictures) == sorted(f"<svg>{pid}:{answer}</svg>" for answer in range(2, 10))


class TestAProcessThatStopsAnswering:
    def test_one_killed_between_renders_is_replaced(self, stand_in: PlantUmlProcess) -> None:
        _picture(stand_in.draw(_block("one"), timeout=10))
        killed = stand_in.pid
        assert killed is not None
        os.kill(killed, 9)
        assert _gone(killed)

        after = _picture(stand_in.draw(_block("two"), timeout=10))

        assert stand_in.pid not in (None, killed)
        assert after == f"<svg>{stand_in.pid}:2</svg>"

    def test_one_that_dies_mid_render_is_replaced_and_the_render_tried_once_more(
        self, stand_in: PlantUmlProcess,
    ) -> None:
        _picture(stand_in.draw(_block("one"), timeout=10))
        died = stand_in.pid

        retried = _picture(stand_in.draw(_block("die-once"), timeout=10))

        assert stand_in.pid != died
        assert retried == f"<svg>{stand_in.pid}:2</svg>"

    def test_a_render_that_kills_every_process_fails_with_the_reason(self, stand_in: PlantUmlProcess) -> None:
        drawing = stand_in.draw(_block("die-always"), timeout=10)

        assert isinstance(drawing, NotDrawn) and drawing.why is WhyNotDrawn.STOPPED
        assert _picture(stand_in.draw(_block("fine"), timeout=10)).startswith("<svg>")

    def test_a_render_past_its_deadline_kills_the_process_and_the_next_render_succeeds(
        self, stand_in: PlantUmlProcess,
    ) -> None:
        _picture(stand_in.draw(_block("one"), timeout=10))
        wedged = stand_in.pid
        assert wedged is not None

        started = time.monotonic()
        drawing = stand_in.draw(_block("hang"), timeout=1)

        assert time.monotonic() - started < 5  # noqa: PLR2004 - the deadline, not the stand-in's sleep
        assert isinstance(drawing, NotDrawn) and drawing.why is WhyNotDrawn.TIMED_OUT
        assert "1 s" in drawing.reason
        assert _gone(wedged)
        assert _picture(stand_in.draw(_block("two"), timeout=10)) == f"<svg>{stand_in.pid}:2</svg>"

    def test_a_command_that_cannot_start_says_so(self, tmp_path: Path) -> None:
        drawing = PlantUmlProcess([str(tmp_path / "no-such-java")]).draw(_block("one"), timeout=5)

        assert isinstance(drawing, NotDrawn) and drawing.why is WhyNotDrawn.NO_JAVA


class TestStopping:
    def test_leaves_no_process_behind(self, stand_in: PlantUmlProcess) -> None:
        _picture(stand_in.draw(_block("one"), timeout=10))
        pid = stand_in.pid
        assert pid is not None

        stand_in.stop()

        assert stand_in.pid is None and _gone(pid)

    def test_does_not_wait_for_a_render_in_flight(self, stand_in: PlantUmlProcess) -> None:
        _picture(stand_in.draw(_block("one"), timeout=10))
        wedged = stand_in.pid
        assert wedged is not None
        outcome: list[Drawn | NotDrawn] = []
        drawing = threading.Thread(target=lambda: outcome.append(stand_in.draw(_block("hang"), timeout=60)))
        drawing.start()
        time.sleep(0.3)

        started = time.monotonic()
        stand_in.stop()

        assert time.monotonic() - started < 5  # noqa: PLR2004 - a stop inside the teardown reserve
        assert _gone(wedged)
        drawing.join(timeout=10)
        assert not drawing.is_alive()
        assert [type(drawn) for drawn in outcome] == [NotDrawn], "a render a stop cut short is not retried"
        assert stand_in.pid is None


class TestAnIdleProcess:
    def test_is_stopped_and_the_next_render_starts_another(self, tmp_path: Path) -> None:
        script = tmp_path / "stand_in.py"
        script.write_text(_STAND_IN, encoding="utf-8")
        process = PlantUmlProcess([sys.executable, str(script), str(tmp_path / "x")], idle_seconds=0.5)
        try:
            _picture(process.draw(_block("one"), timeout=10))
            idle = process.pid
            assert idle is not None

            assert _gone(idle)
            assert process.pid is None
            assert _picture(process.draw(_block("two"), timeout=10)) == f"<svg>{process.pid}:2</svg>"
        finally:
            process.stop()

    def test_is_kept_while_renders_keep_coming(self, tmp_path: Path) -> None:
        script = tmp_path / "stand_in.py"
        script.write_text(_STAND_IN, encoding="utf-8")
        process = PlantUmlProcess([sys.executable, str(script), str(tmp_path / "x")], idle_seconds=1.0)
        try:
            pids = set()
            for word in ("one", "two", "three", "four", "five"):
                _picture(process.draw(_block(word), timeout=10))
                pids.add(process.pid)
                time.sleep(0.4)

            assert len(pids) == 1
        finally:
            process.stop()


class TestWhatALiveProcessIsGiven:
    @pytest.mark.parametrize(
        ("source", "block"),
        [
            ("---\nname: x\n---\n@startuml\nA -> B\n@enduml\ntrailing\n", "@startuml\nA -> B\n@enduml\n"),
            ("@startuml name\nA -> B\n@enduml", "@startuml name\nA -> B\n@enduml\n"),
            ("@startmindmap\n* a\n@endmindmap\n", "@startmindmap\n* a\n@endmindmap\n"),
        ],
    )
    def test_exactly_one_block(self, source: str, block: str) -> None:
        assert single_block(source) == block

    @pytest.mark.parametrize(
        "source",
        [
            "no diagram at all\n",
            "@startuml\nA -> B\n",
            "@startuml\nA -> B\n@enduml\n@startuml\nC -> D\n@enduml\n",
            "  @startuml\nA -> B\n@enduml\n",
        ],
    )
    def test_nothing_that_would_spill_into_the_next_diagram(self, source: str) -> None:
        assert single_block(source) is None
