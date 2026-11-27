"""The identity this server acts as: the author of its commits and the recorder of its judgements.

There is no principal yet, so whatever the server records as having been done by someone — a commit,
an FMEA factor judgement, a VEX assessment — is attributed to this configured identity, never to a
name a request supplies. When a principal exists it takes this role, and this stays the committer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_SERVICE_NAME = "Architecture Repository Service"
_DEFAULT_SERVICE_EMAIL = "arch-service@localhost"


@dataclass(frozen=True)
class GitIdentity:
    name: str
    email: str

    @property
    def attribution(self) -> str:
        """The identity as one line, the way git prints an author: `Name <email>`."""
        return f"{self.name} <{self.email}>"


def load_service_git_identity() -> GitIdentity:
    """Load the non-interactive service identity (`ARCH_GIT_AUTHOR_NAME`, `ARCH_GIT_AUTHOR_EMAIL`)."""
    return GitIdentity(
        name=os.getenv("ARCH_GIT_AUTHOR_NAME", "").strip() or _DEFAULT_SERVICE_NAME,
        email=os.getenv("ARCH_GIT_AUTHOR_EMAIL", "").strip() or _DEFAULT_SERVICE_EMAIL,
    )


def recording_identity() -> str:
    """Who the server records as having made a judgement it stores: the configured identity."""
    return load_service_git_identity().attribution
