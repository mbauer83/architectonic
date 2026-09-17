"""A backend instance says how it serves, so a restart can say the same.

`--port` was already read off a live backend's argv; `--admin-mode`, `--read-only` and `--host` were
not, so anything restarting a backend from what it observed would bring a read-only review deployment
back writable. The flags are kept as argv tokens, values beside their flag, in the order given.
"""

from __future__ import annotations

from src.infrastructure.backend.backend_process import serving_flags


def test_the_posture_flags_are_kept_and_the_rest_dropped() -> None:
    argv = ["arch-backend", "--repo-root", "/r", "--admin-mode", "--port", "8123", "--read-only", "--daemon"]
    assert serving_flags(argv) == ["--admin-mode", "--read-only"]


def test_the_host_keeps_its_value() -> None:
    assert serving_flags(["arch-backend", "--host", "0.0.0.0", "--port", "8000"]) == ["--host", "0.0.0.0"]


def test_a_trailing_host_with_no_value_is_not_invented() -> None:
    assert serving_flags(["arch-backend", "--host"]) == []


def test_a_plain_backend_carries_no_flags() -> None:
    assert serving_flags(["python", "-m", "src.infrastructure.backend.arch_backend", "--port", "8000"]) == []
