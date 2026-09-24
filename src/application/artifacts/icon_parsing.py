"""An icon file, as an index record: the file's own reading, and None where it cannot be read.

A file that is not a readable icon is left out of the index as a malformed document is; the verifier
is what says why.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.icons.icon_file import IconFile, read_icon_file
from src.domain.icons.icon_record import IconRecord


def parse_icon(path: Path) -> IconRecord | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match read_icon_file(text):
        case IconFile(metadata=metadata):
            return IconRecord(metadata, path)
        case _:
            return None
