"""Fetching an asset this project does not carry, and proving it is the one that was pinned.

Three provisioning commands acquire something the repository deliberately does not hold — the
PlantUML jar, the Graphviz source, the embedding model's weights. Each of them downloads bytes,
takes their SHA-256 and refuses when it is not the digest that was pinned. That is one operation,
so it is written once: a second copy is where two commands start disagreeing about what "verified"
means, and the digest check is the only thing standing between a provisioning step and running
whatever a compromised mirror served.

`urlopen` is called on URLs this module's callers pin as constants, never on anything a user or a
repository supplies; the suppression records that the scheme is not attacker-controlled.
"""

from __future__ import annotations

import hashlib
import urllib.request

_USER_AGENT = "architectonic-bootstrap/1.0"


def sha256_hex(data: bytes) -> str:
    """The digest a pinned asset is identified by, lowercase hex."""
    return hashlib.sha256(data).hexdigest().lower()


def download_bytes(url: str, *, label: str | None = None) -> bytes:
    """Fetch `url`. A `label` narrates the download; without one the fetch is silent.

    A failure ends the command rather than returning something empty: every caller is a
    provisioning step whose whole purpose is the bytes.
    """
    if label is not None:
        print(f"  {label}: {url} … ", end="", flush=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request) as response:  # noqa: S310 — pinned URL, see module docstring
            data = response.read()
    except Exception as exc:
        if label is not None:
            print("FAILED")
        raise SystemExit(f"Download error: {url}: {exc}") from exc
    if label is not None:
        print(f"{len(data):,} bytes")
    return data


def download_verified(url: str, *, expected_sha256: str, label: str | None = None) -> bytes:
    """Fetch `url` and return its bytes only when they hash to `expected_sha256`.

    Nothing is written here. A caller that has not received bytes back has nothing to install,
    which is what keeps a mismatch from leaving a half-provisioned tree behind.
    """
    data = download_bytes(url, label=label)
    actual = sha256_hex(data)
    expected = expected_sha256.lower()
    if actual != expected:
        raise SystemExit(
            f"SHA-256 mismatch for {url} — nothing written\n  expected : {expected}\n  actual   : {actual}"
        )
    return data
