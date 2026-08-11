"""How this project parses YAML — one loader, chosen once.

The repository is markdown with YAML frontmatter (ADR@1780761609), so parsing YAML is not an
incidental concern here: a verification pass over 880 files parses ~200,000 YAML documents, and a
profile put the pass's time in `yaml/scanner.py`. Every call site used `yaml.safe_load`, which is the
**pure-Python** loader, even though `libyaml` is present in this environment and PyYAML ships a C
loader with identical semantics.

Measured on this repository's own corpus — 1,514 documents, 470 KB, every frontmatter block, every
fenced YAML block and every ontology file:

| Loader | Median of five interleaved runs |
| --- | --- |
| `SafeLoader` (pure Python) | 377 ms |
| `CSafeLoader` (libyaml) | 40 ms |

**9.5x**, and 0 of the 1,514 documents parse to a different value under the two loaders.

Beyond speed: the pure-Python loader holds the GIL throughout, which is why the verification pool was
counterproductive and why `_DEFAULT_PASS_WORKERS` is 1. The C loader releases it, so the worker count
is worth re-measuring — but from the table, not from this docstring.

Living in `src/domain/` because the dependency policy lets `domain` import only `domain`, and domain
modules parse YAML too; a loader anywhere else could not be the single owner. `clock.py` is the
precedent for a technical primitive at this level.

Parsing only. Serialisation (`yaml.safe_dump`, 22 sites) has an equivalent C dumper and is not
measured, so it keeps its own call sites rather than being changed on speculation.
"""

from __future__ import annotations

from typing import IO, Any

import yaml

try:
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # pragma: no cover - an install whose PyYAML was built without libyaml
    # Not a failure: the pure-Python loader is what every call site used until now, so a machine
    # without libyaml keeps exactly today's behaviour rather than losing the ability to read a file.
    from yaml import SafeLoader as _SafeLoader  # type: ignore[assignment]

#: Which loader the import above resolved to. Public because the choice is otherwise unobservable —
#: the two loaders agree on every result, which is the point, so nothing about a parsed value reveals
#: which one ran. That makes this the only way to assert that the fast path was taken, and the answer
#: to "why is verification slow on this machine".
USES_LIBYAML = _SafeLoader is not yaml.SafeLoader


def parse_yaml(source: str | bytes | IO[str] | IO[bytes]) -> Any:
    """Parse one YAML document, safely, with the fastest loader this install has.

    Accepts what `yaml.safe_load` accepts — text, bytes, or an open file — and raises what it raises,
    `yaml.YAMLError`, whose subclasses are the same from either loader. Call sites that catch
    `yaml.YAMLError` are unaffected by which loader was chosen.

    The return type mirrors `yaml.safe_load` rather than narrowing to `object`. A YAML document may be
    any of a mapping, a sequence, a scalar or `None`, and every call site already narrows what it
    expects; typing this `object` would move 77 unrelated `isinstance` changes into a performance fix.
    Narrowing belongs with the caller that knows the shape it asked for.
    """
    return yaml.load(source, Loader=_SafeLoader)
