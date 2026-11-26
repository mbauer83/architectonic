"""What PlantUML drew for a source this process gave it before, so the same source is not drawn twice.

Drawing a diagram of hundreds of elements costs PlantUML seconds, and one save of an arrangement draws
the same body three times over: once when the editor read the picture, once to verify the write and once
for the rendered outputs. Arranging changes the layout block, which PlantUML never reads, so all three
are the picture it drew already. Measured on a 259-element view: about seven seconds a drawing.

PlantUML draws the same picture of the same source, so a picture is kept by everything that decides it
— the source as PlantUML is given it, the output format and settings, and which PlantUML, Java and
GraphViz drew it — and handed back for the same again. Only a picture is kept: a refusal or a failure
is asked again, so a source fixed in the meantime is drawn and one still broken reports itself. A
source that names a file (`!include`) is never kept, since the file can change under the same text.

Bounded: the few most recently drawn, which is what an editing session asks for.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path

#: How many pictures are kept: a session arranges one diagram, read and saved over and over.
CAPACITY = 8

#: The directives by which a source draws in another file, whose content the source text does not fix.
_NAMES_A_FILE = ("!include", "!import")


class DrawnPictures:
    """The most recently drawn pictures, by what decided them."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self._capacity = capacity
        self._kept: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def recall(self, key: str | None) -> bytes | None:
        """The picture drawn for *key* before, or None."""
        if key is None:
            return None
        with self._lock:
            picture = self._kept.get(key)
            if picture is not None:
                self._kept.move_to_end(key)
            return picture

    def keep(self, key: str | None, picture: bytes) -> None:
        """Keep *picture* as what *key* draws, letting the least recently asked go beyond the capacity."""
        if key is None:
            return
        with self._lock:
            self._kept[key] = picture
            self._kept.move_to_end(key)
            while len(self._kept) > self._capacity:
                self._kept.popitem(last=False)

    def forget(self) -> None:
        """Keep nothing: what a test that fakes the renderer starts from."""
        with self._lock:
            self._kept.clear()


#: The one store this process keeps pictures in.
DRAWN = DrawnPictures()


def _identity(path: Path | None) -> str:
    """A program's path and the size and time of its file, so a replaced program is another drawer."""
    if path is None:
        return "-"
    try:
        stat = path.stat()
    except OSError:
        return str(path)
    return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"


def picture_key(source: str, *settings: str, jar: Path | None, dot: Path | None, java: str) -> str | None:
    """What decides the picture PlantUML draws of *source*; None where the source names a file."""
    if any(directive in source for directive in _NAMES_A_FILE):
        return None
    digest = hashlib.sha256()
    for part in (_identity(jar), _identity(dot), java, *settings, source):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
