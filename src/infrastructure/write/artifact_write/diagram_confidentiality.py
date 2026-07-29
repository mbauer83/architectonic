"""Confidentiality routing for assurance diagram sources.

Rule G-f keeps *rendered* assurance images off disk. The same confidentiality boundary must
cover the diagram *source*: an assurance diagram whose classification is above the
publishability ceiling carries sensitive analysis content (bowtie/GSN/UCA node labels) in its
frontmatter and PUML body, so its `.puml` must not land in the git-tracked catalog.

Confidentiality is driven by the TLP classification (see ``src.domain.assurance.classification``), not a
blanket per-type flag: an assurance diagram explicitly classified TLP:WHITE/GREEN is
publishable (renders and persists to the catalog like any diagram — this is what lets the
self-describing model ship a public assurance example), while anything above that, or
unclassified, is confidential and is redirected to a gitignored location.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.domain.assurance.classification import is_publishable


@lru_cache(maxsize=1)
def _assurance_diagram_type_names() -> frozenset[str]:
    """Names of all assurance (module_class == 'assurance') diagram types in the COMPLETE vocabulary.

    Resolved against the complete module registry, not the active one, so a diagram type's
    confidentiality classification is independent of whether the confidential store happens to
    be unlocked. Otherwise a store-less host would mis-classify an existing assurance diagram
    as non-confidential and could leak its source/render — the exact opposite of the gate's intent.
    """
    try:
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        registry = build_module_registry(complete_vocabulary=True)
    except Exception:  # noqa: BLE001
        return frozenset()
    return frozenset(
        str(name)
        for name, dt in registry.all_diagram_types().items()
        if getattr(dt, "module_class", None) == "assurance"
    )


def is_assurance_diagram_type(diagram_type: str) -> bool:
    """True if *diagram_type* belongs to the assurance module (module_class == 'assurance')."""
    return diagram_type in _assurance_diagram_type_names()


def is_confidential_diagram_source(diagram_type: str, tlp: str | None) -> bool:
    """True if this diagram's source must be kept out of the shared catalog.

    Assurance-only types default to confidential when unclassified. GSN is dual-home:
    unclassified GSN is general architecture content, while an explicitly classified GSN
    published through the assurance bridge is gated above the publishable ceiling.
    """
    if diagram_type == "gsn":
        return tlp is not None and not is_publishable(tlp)
    return is_assurance_diagram_type(diagram_type) and not is_publishable(tlp)


def ensure_confidential_gitignore(confidential_root: Path) -> None:
    """Write a self-contained ``.gitignore`` so the confidential dir's contents never reach git.

    A ``*`` ignore travels with the directory regardless of which git repo encloses the
    engagement, protecting the authoring machine from accidentally committing confidential
    diagram sources. Idempotent.
    """
    confidential_root.mkdir(parents=True, exist_ok=True)
    gitignore = confidential_root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# Confidential assurance diagram sources — never commit.\n*\n", encoding="utf-8")
