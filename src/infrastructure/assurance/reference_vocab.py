"""Reference vocabulary loader for assurance classification schemes.

Loads STRIDE, ISO 26262, ISO 21434, and any user-supplied catalogs from
.arch-repo/reference/<scheme>.<version>.yaml (user-supplied) or from the
bundled seeds in src/ontologies/assurance/reference_vocab/ (defaults).

New/updated catalogs ship as data-only updates — no code or ontology changes.
Validation is tolerant: unknown schemes are treated as free-form.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_BUNDLED_VOCAB_DIR = Path(__file__).parent.parent.parent / "ontologies" / "assurance" / "reference_vocab"


@lru_cache(maxsize=32)
def _load_vocab(path: Path) -> dict[str, object]:
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh)
        return dict(data) if isinstance(data, dict) else {}
    except OSError:
        logger.debug("Vocab file not found: %s", path)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load vocab %s: %s", path, exc)
        return {}


def _vocab_paths(scheme: str, repo_root: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if repo_root:
        ref_dir = repo_root / ".arch-repo" / "reference"
        for p in sorted(ref_dir.glob(f"{scheme}.*.yaml")) if ref_dir.exists() else []:
            paths.append(p)
    bundled = _BUNDLED_VOCAB_DIR / f"{scheme}.yaml"
    if bundled.exists():
        paths.append(bundled)
    return paths


def validate_classification(
    scheme: str,
    code: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, object]:
    """Validate a (scheme, code) classification pair.

    Returns:
        {"valid": True, "label": ..., "description": ...} on success
        {"valid": False, "reason": ...} when the code is unknown
        {"valid": True, "free_form": True} when the scheme is unknown (tolerant)
    """
    paths = _vocab_paths(scheme, repo_root)
    if not paths:
        return {"valid": True, "free_form": True, "scheme": scheme, "code": code}

    for path in paths:
        vocab = _load_vocab(path)
        codes: dict[str, object] = {}
        for key in ("codes", "key_clauses", "integrity_levels", "assurance_levels"):
            section = vocab.get(key)
            if isinstance(section, dict):
                codes.update(section)
        if code in codes:
            entry = codes[code]
            if isinstance(entry, dict):
                return {
                    "valid": True,
                    "scheme": scheme,
                    "code": code,
                    "label": entry.get("label", code),
                    "description": entry.get("description", ""),
                }
            return {"valid": True, "scheme": scheme, "code": code}

    return {
        "valid": False,
        "scheme": scheme,
        "code": code,
        "reason": f"Code '{code}' not found in {scheme} vocabulary.",
    }


def list_schemes(*, repo_root: Path | None = None) -> list[str]:
    schemes: set[str] = set()
    if repo_root:
        ref_dir = repo_root / ".arch-repo" / "reference"
        if ref_dir.exists():
            for p in ref_dir.glob("*.yaml"):
                schemes.add(p.stem.split(".")[0])
    if _BUNDLED_VOCAB_DIR.exists():
        for p in _BUNDLED_VOCAB_DIR.glob("*.yaml"):
            schemes.add(p.stem)
    return sorted(schemes)


def load_scheme(scheme: str, *, repo_root: Path | None = None) -> dict[str, object]:
    """Return the full vocab dict for a scheme (first match wins)."""
    paths = _vocab_paths(scheme, repo_root)
    for p in paths:
        data = _load_vocab(p)
        if data:
            return data
    return {}
