"""Write the backend's OpenAPI document to a file, in-process.

The frontend's contract check needs the document before a backend exists: it runs *before* the
commit, and the gate that starts a server runs after it. A check that depended on that server
could not be run at the moment it is meant to protect. So the document is produced by building
the application object and asking it for its schema — no socket, no port, no lifespan.

Usage:
    uv run tools/openapi/dump_openapi.py <output.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    from src.infrastructure.backend.arch_backend_app import _build_app

    document = _build_app().openapi()
    destination = Path(argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
