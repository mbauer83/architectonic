"""An ssh remote on this machine whose key needs a passphrase, without sshd or a real key.

`install(directory, passphrase)` writes a stand-in for `ssh` and returns the environment that makes
git use it. The stand-in behaves like OpenSSH with a passphrase-protected key and no agent: it asks
`SSH_ASKPASS` for the passphrase when `SSH_ASKPASS_REQUIRE=force` says to, and otherwise has none.
With the right passphrase it runs the requested `git-receive-pack` / `git-upload-pack` against the
path in the URL; with any other it answers as a server does, `Permission denied (publickey).`

Remote URLs take the scp form `fake@localhost:<absolute path of a bare repository>`.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

_SCRIPT = """#!/bin/sh
# Stand-in for ssh: <host> <command>. See tests/support/fake_ssh_remote.py.
host="$1"; shift
expected=$(cat {expected})
given=""
if [ -n "$SSH_ASKPASS" ] && [ "$SSH_ASKPASS_REQUIRE" = "force" ]; then
  given=$("$SSH_ASKPASS" "Enter passphrase for key '/home/fixture/.ssh/id_ed25519': ")
fi
if [ "$given" != "$expected" ]; then
  echo "$host: Permission denied (publickey)." >&2
  exit 255
fi
exec sh -c "$*"
"""


def install(directory: Path, passphrase: str) -> dict[str, str]:
    """Write the stand-in into `directory`; return the variables that point git at it."""
    directory.mkdir(parents=True, exist_ok=True)
    expected = directory / "expected-passphrase"
    expected.write_text(passphrase, encoding="utf-8")
    script = directory / "fake-ssh"
    script.write_text(_SCRIPT.format(expected=shlex.quote(str(expected))), encoding="utf-8")
    script.chmod(0o700)
    return {"GIT_SSH_COMMAND": str(script), "GIT_SSH_VARIANT": "simple"}


def ssh_url(bare: Path) -> str:
    """The scp-form URL the stand-in serves `bare` under."""
    return f"fake@localhost:{os.fspath(bare.resolve())}"
