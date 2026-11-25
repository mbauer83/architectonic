"""The container image runs as an unprivileged user and says whether it is healthy.

Both were in the `Dockerfile` already; nothing held them there. The health probe is also checked
against the host list the backend answers to: a probe addressed by a name the backend refuses would
report a healthy container as failing.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from src.config.allowed_hosts import LOOPBACK_HOSTS, AllowedHosts
from tests.support.source_paths import REPO_ROOT

_DOCKERFILE = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")


def _runtime_stage() -> str:
    return _DOCKERFILE.split(" AS runtime", 1)[1]


def test_the_runtime_stage_switches_to_an_unprivileged_user() -> None:
    users = re.findall(r"^USER\s+(\S+)", _runtime_stage(), flags=re.MULTILINE)

    assert users, "the runtime stage never leaves root"
    assert users[-1] not in {"root", "0", "0:0"}


def test_the_image_declares_a_health_check_the_backend_will_answer() -> None:
    match = re.search(r"^HEALTHCHECK\b.*?CMD\s+(.+?)$", _runtime_stage(), flags=re.MULTILINE | re.DOTALL)

    assert match, "the runtime stage declares no HEALTHCHECK"
    url = re.search(r"https?://\S+", match.group(1))
    assert url, match.group(1)
    assert AllowedHosts(entries=LOOPBACK_HOSTS).permits(urlsplit(url.group(0)).netloc)
