"""The revision of a piece of content: one digest function, stated once.

A revision answers "is this still what I read?" without keeping what was read. A diagram edit sends
back the revision of the file it started from, and a change set records the revision of a prose field
it replaces — the same question, so the same function. Two spellings would be two digests that
cannot be compared, discovered the first time one surface handed its revision to the other.

Sixteen hexadecimal characters of SHA-256: detection, not security. Nothing here defends against a
chosen collision, and nothing that uses it needs to.
"""

from __future__ import annotations

import hashlib

#: How much of the digest is kept. Named because a stored revision is compared with a computed one,
#: and a reader that kept a different length would find every one of them stale.
_LENGTH = 16


def content_revision(content: bytes) -> str:
    """The revision of *content*: the first sixteen hex characters of its SHA-256."""
    return hashlib.sha256(content).hexdigest()[:_LENGTH]
