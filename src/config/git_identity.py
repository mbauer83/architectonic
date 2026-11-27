from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_SERVICE_NAME = "Architecture Repository Service"
_DEFAULT_SERVICE_EMAIL = "arch-service@localhost"


@dataclass(frozen=True)
class GitIdentity:
    name: str
    email: str


def load_service_git_identity() -> GitIdentity:
    """Load the non-interactive service identity used as git committer."""
    return GitIdentity(
        name=os.getenv("ARCH_GIT_AUTHOR_NAME", "").strip() or _DEFAULT_SERVICE_NAME,
        email=os.getenv("ARCH_GIT_AUTHOR_EMAIL", "").strip() or _DEFAULT_SERVICE_EMAIL,
    )
