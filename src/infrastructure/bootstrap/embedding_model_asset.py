"""The embedding model as an installed asset: what it is, where it goes, and whether it is intact.

A lock file records Python distributions; it does not record a model file. So the weights get the
answer a locked distribution would otherwise have given them — a pinned revision, a digest per file,
and a refusal when what arrived is not what was pinned.

Three files are enough to encode offline, measured rather than assumed: the remaining files in the
upstream repository serve tooling this project does not run. The whole asset is about 31 MB and is
deliberately not committed here, so a checkout is small and the digests below are what make an
acquired copy trustworthy.

Nothing in this module is required for the product to answer a query. A missing, incomplete or
corrupt install disables vector retrieval and says which file failed; keyword search is unaffected,
which is the whole of what the product promises without the weights.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.bootstrap.asset_download import sha256_hex
from src.infrastructure.bootstrap.project_layout import project_directory


@dataclass(frozen=True)
class PinnedFile:
    """One file of the asset, named as upstream names it, with the digest it must hash to."""

    name: str
    sha256: str


#: The upstream model, pinned to a commit rather than a branch: a tag can move, a commit cannot.
MODEL_ID = "minishlab/potion-base-8M"
MODEL_REVISION = "bf8b056651a2c21b8d2565580b8569da283cab23"
MODEL_LICENSE = "MIT"

#: Exactly the files an offline load reads. Adding one means adding its digest.
MODEL_FILES: tuple[PinnedFile, ...] = (
    PinnedFile("config.json", "2a6ac0e9aaa356a68a5688070db78fc3a464fefe85d2f06a1905ce3718687553"),
    PinnedFile("model.safetensors", "f65d0f325faadc1e121c319e2faa41170d3fa07d8c89abd48ca5358d9a223de2"),
    PinnedFile("tokenizer.json", "e67e803f624fb4d67dea1c730d06e1067e1b14d830e2c2202569e3ef0f70bb50"),
)

#: Where the asset is installed, relative to the directory holding `pyproject.toml`. Anything that
#: writes or looks for the weights reads this rather than spelling a path of its own.
MODEL_RELPATH = "models/potion-base-8M"

#: Names a directory to use instead, so several checkouts on one machine can share one 31 MB copy.
ENV_MODEL_DIRECTORY = "ARCH_EMBEDDING_MODEL_DIR"


def file_url(pinned: PinnedFile) -> str:
    """Where one pinned file is fetched from, addressed by revision so the URL cannot drift."""
    return f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{pinned.name}"


def model_directory() -> Path:
    """Where the asset belongs — whether or not anything is installed there yet."""
    named = os.environ.get(ENV_MODEL_DIRECTORY, "").strip()
    return Path(named).expanduser().resolve() if named else project_directory() / MODEL_RELPATH


def installed_model_directory() -> Path | None:
    """The directory when every pinned file is present in it, otherwise None.

    Presence only. Hashing 30 MB is what `integrity_failures` is for, and a caller that wants to
    know whether to bother reading at all should not pay for it.
    """
    directory = model_directory()
    present = all((directory / pinned.name).is_file() for pinned in MODEL_FILES)
    return directory if present else None


def integrity_failures(directory: Path | None = None) -> tuple[str, ...]:
    """What is wrong with the install, as sentences, or an empty tuple when it is intact.

    Missing and corrupt are reported together and per file, because a caller disabling vector
    retrieval wants to tell its operator everything that needs fixing, not the first thing.
    """
    root = directory if directory is not None else model_directory()
    inspected = (_failure(root / pinned.name, pinned) for pinned in MODEL_FILES)
    return tuple(failure for failure in inspected if failure is not None)


def _failure(path: Path, pinned: PinnedFile) -> str | None:
    if not path.is_file():
        return f"{pinned.name}: missing from {path.parent}"
    actual = sha256_hex(path.read_bytes())
    if actual != pinned.sha256:
        return f"{pinned.name}: digest {actual} does not match the pinned {pinned.sha256}"
    return None
