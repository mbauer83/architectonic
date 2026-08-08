"""The filesystem watcher enqueues a refresh intent without holding the workspace gate.

It used to take exclusive WRITE around ``enqueue_background_refresh``, which sets ``pending_full``
or unions ``pending_paths``, bumps a debounce stamp, and starts a worker if none is alive. That is
bookkeeping on the refresh queue — it mutates a queue, not the workspace — and the queue serialises
itself on its own condition. So the acquisition guarded work that never touched the resource the
gate protects, while colliding with every long read: a poller blocked for minutes behind a
verification, for nothing.
"""

from __future__ import annotations

import threading
from pathlib import Path

from src.infrastructure.mcp.artifact_mcp import watch_tools
from src.infrastructure.workspace.mutation_gate import get_workspace_gate


class TestTheWatcherDoesNotCompeteWithWriters:
    def test_a_refresh_is_enqueued_while_a_write_holds_the_gate(self, tmp_path: Path) -> None:
        """The property that matters: a held write gate does not stall the poller."""
        enqueued = threading.Event()
        roots = [tmp_path]

        def _enqueue() -> None:
            watch_tools.enqueue_background_refresh(roots, full_refresh=True)
            enqueued.set()

        with get_workspace_gate().writing():
            worker = threading.Thread(target=_enqueue, daemon=True)
            worker.start()
            assert enqueued.wait(timeout=5), "enqueue blocked while a write gate was held"
        worker.join(timeout=5)

    def test_the_watcher_module_holds_no_reference_to_the_gate(self) -> None:
        """Asserted structurally so the acquisition cannot return 'for symmetry'."""
        source = Path(watch_tools.__file__).read_text(encoding="utf-8")

        assert "get_workspace_gate" not in source
        assert "mutation_gate" not in source
