from __future__ import annotations

import logging

from src.infrastructure.backend.arch_backend_app import _log_slow_request_warning


def test_slow_request_warning_includes_queue_metadata(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(
        "src.infrastructure.backend.arch_backend_app.get_write_queue_state_snapshot",
        lambda: {
            "active_jobs": 1,
            "pending_jobs": 2,
            "active_tool_name": "artifact_bulk_write",
            "active_operation_id": "op_123",
            "active_phase": "verify",
        },
    )

    with caplog.at_level(logging.WARNING):
        _log_slow_request_warning(method="POST", path="/mcp/write", threshold_s=5.0)

    assert "HTTP request still running" in caplog.text
    assert "artifact_bulk_write" in caplog.text
    assert "op_123" in caplog.text
    assert "verify" in caplog.text
