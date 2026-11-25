"""The perspectives a repository offers whoever writes stressors: the shipped frameworks, extended by its own.

A repository states its own in `.arch-repo/stress-perspectives.json`:

    {"frameworks": [{"id": "regulation", "name": "Regulation",
                     "perspectives": [{"name": "Data residency", "question": "What if …?"}]}]}

A framework with a shipped framework's id takes that framework's place; any other is offered after the
shipped ones. Without the file the shipped frameworks are offered as they are. A file that cannot be read
as this shape is refused, saying where, rather than skipped: a deployment that extended the vocabulary
and silently lost the extension would read coverage against the wrong list.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.domain.repository.repo_default_stress_perspectives import (
    PerspectiveFramework,
    declared_framework,
    with_frameworks,
)
from src.domain.repository.repo_layout import ARCH_REPO

#: Where a repository states the frameworks it adds to, or puts in place of, the shipped ones.
PERSPECTIVES_FILE = "stress-perspectives.json"


class UnreadablePerspectives(ValueError):
    """The repository's perspectives file is not the shape it is read as."""


def repository_perspectives(root: Path) -> tuple[PerspectiveFramework, ...]:
    """The frameworks *root* offers: the shipped ones, with the repository's own laid over them."""
    path = root / ARCH_REPO / PERSPECTIVES_FILE
    if not path.is_file():
        return with_frameworks(())
    try:
        stated = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as unreadable:
        raise UnreadablePerspectives(f"{path} cannot be read as JSON: {unreadable}") from unreadable
    frameworks = stated.get("frameworks") if isinstance(stated, Mapping) else None
    if not isinstance(frameworks, list):
        raise UnreadablePerspectives(f"{path} states no list of frameworks under \"frameworks\".")
    return with_frameworks(_framework(path, at, one) for at, one in enumerate(frameworks))


def _framework(path: Path, at: int, stated: Any) -> PerspectiveFramework:
    where = f"{path}, framework {at + 1}"
    if not isinstance(stated, Mapping):
        raise UnreadablePerspectives(f"{where} is not an object.")
    key, name, perspectives = stated.get("id"), stated.get("name"), stated.get("perspectives")
    if not (isinstance(key, str) and key.strip() and isinstance(name, str) and name.strip()):
        raise UnreadablePerspectives(f"{where} needs an id and a name.")
    if not isinstance(perspectives, list) or not perspectives:
        raise UnreadablePerspectives(f"{where} ({key}) lists no perspectives.")
    return declared_framework(key.strip(), name.strip(), *(_perspective(where, one) for one in perspectives))


def _perspective(where: str, stated: Any) -> tuple[str, str]:
    name = stated.get("name") if isinstance(stated, Mapping) else None
    question = stated.get("question") if isinstance(stated, Mapping) else None
    if not (isinstance(name, str) and name.strip() and isinstance(question, str) and question.strip()):
        raise UnreadablePerspectives(f"{where}: every perspective needs a name and a guiding question.")
    return name.strip(), question.strip()
