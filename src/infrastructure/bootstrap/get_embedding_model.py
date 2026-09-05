"""Download and verify the embedding model this deployment encodes with.

Usage
-----
    get-embedding-model                # install the pinned revision, skipping what is already there
    get-embedding-model --force        # re-download every file
    get-embedding-model --check        # report whether the installed asset is intact, download nothing
    get-embedding-model --output DIR   # install somewhere other than the default

The default location is `models/potion-base-8M` beside `pyproject.toml`, or whatever
`ARCH_EMBEDDING_MODEL_DIR` names — several checkouts on one machine can share a single copy.

Nothing here is needed to run the product. Without the asset, vector retrieval is off and keyword
search answers as it always has.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.infrastructure.bootstrap.asset_download import download_verified
from src.infrastructure.bootstrap.embedding_model_asset import (
    MODEL_FILES,
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_REVISION,
    PinnedFile,
    file_url,
    integrity_failures,
    model_directory,
)


def _install_file(pinned: PinnedFile, directory: Path, *, force: bool) -> bool:
    """Fetch one file unless an intact copy is already there. True when bytes were written."""
    destination = directory / pinned.name
    if destination.is_file() and not force:
        print(f"  {pinned.name}: already present")
        return False
    data = download_verified(file_url(pinned), expected_sha256=pinned.sha256, label=pinned.name)
    directory.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return True


def install(directory: Path, *, force: bool) -> int:
    print(f"Embedding model {MODEL_ID} @ {MODEL_REVISION[:12]} ({MODEL_LICENSE}) → {directory}")
    written = [pinned.name for pinned in MODEL_FILES if _install_file(pinned, directory, force=force)]

    # An install that skipped files is only trustworthy if what it skipped is what was pinned, so
    # the digests are re-read from disk rather than inferred from the downloads that just passed.
    failures = integrity_failures(directory)
    if failures:
        print("\nThe installed asset is not intact:")
        for failure in failures:
            print(f"  {failure}")
        print("\nRe-run with --force to replace what is already there.")
        return 1

    print(f"OK  {len(written)} file(s) downloaded, {len(MODEL_FILES)} verified")
    return 0


def check(directory: Path) -> int:
    failures = integrity_failures(directory)
    if failures:
        print(f"Embedding model not usable at {directory}:")
        for failure in failures:
            print(f"  {failure}")
        print("\nRun get-embedding-model to install it. Keyword search is unaffected.")
        return 1
    print(f"Embedding model OK at {directory} ({MODEL_ID} @ {MODEL_REVISION[:12]})")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output", default=None, metavar="DIR", help="Install location (default: see above)")
    parser.add_argument("--force", action="store_true", help="Re-download every file")
    parser.add_argument("--check", action="store_true", help="Verify the installed asset without downloading")
    args = parser.parse_args(argv)

    directory = Path(args.output).expanduser().resolve() if args.output else model_directory()
    sys.exit(check(directory) if args.check else install(directory, force=args.force))


if __name__ == "__main__":
    main()
