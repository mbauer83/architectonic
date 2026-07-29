"""Shared git SSH environment, populated by GitSyncManager on startup.

Both the async background sync (git_sync.py) and the synchronous enterprise
git operations (enterprise_git_ops.py) read from this module so they use the
same askpass credentials without duplicating the setup logic.
"""

from __future__ import annotations

_ssh_env: dict[str, str] | None = None


def set_ssh_env(env: dict[str, str] | None) -> None:
    global _ssh_env
    _ssh_env = env


def get_ssh_env() -> dict[str, str] | None:
    """Return the configured SSH environment, or None to inherit the process environment."""
    return _ssh_env
