"""Where a body PlantUML is given as a file is put: a directory of its own, outside every repository.

PlantUML reads its input from a file, so every render from a body writes one. Those files used to be
written into the diagram catalog, beside the diagrams, on the grounds that PlantUML resolves an
`!include` against the including file's directory. That stopped being true of anything this product
renders: the managed fragments are expanded into the body before PlantUML runs, the only include a
prepared body still carries is the standard library's `<…>` form, which PlantUML reads from its own
jar, and PlantUML runs under the sandbox profile, which reads no file an include names. The location
bought nothing, and it cost this: a render killed mid-way skipped its `finally`, left its scratch
file in the catalog under a name the kind table reads as a diagram's, and git did not ignore it.

A scratch file here is one that is gone with its directory, and a directory the operating system's
temporary area owns even when the process is killed before it can remove it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: What every scratch directory is called before its random part, so a leftover one is recognisable.
SCRATCH_PREFIX = "arch-plantuml-"


@contextmanager
def plantuml_input(body: str) -> Iterator[Path]:
    """*body* as the file PlantUML is given, alone in a new directory that is removed on exit.

    The file's stem is the directory's random name. PlantUML names its output after its input, and
    a caller writing that output into a directory other renders share needs a name no overlapping
    render uses. Run PlantUML with this file's directory as its working directory: PlantUML resolves
    `-o` against it and against the input's directory, and they must be the same one.
    """
    with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
        directory = Path(scratch)
        path = directory / f"{directory.name}.puml"
        path.write_text(body, encoding="utf-8")
        yield path
