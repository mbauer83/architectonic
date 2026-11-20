"""Reference vocabulary loader for assurance classification schemes.

Loads STRIDE, ISO 26262, ISO 21434, and any user-supplied catalogs from
.arch-repo/reference/<scheme>.<version>.yaml (user-supplied) or from the
bundled seeds in src/ontologies/assurance/reference_vocab/ (defaults).

New/updated catalogs ship as data-only updates — no code or ontology changes.
Validation is tolerant: unknown schemes are treated as free-form.

A *scheme* here is one catalogue: the file's name, under which its entries are looked up. It is the
word for what STRIDE is — a classification scheme, whose entries classify a hazard — and it is kept
for that reason. A catalogue of a standard also lists that standard's key clauses, and those are
what an obligation cites: `provisions_by_source` reads that one section, for the obligation whose
`source` names the catalogue. An obligation's source is therefore not a scheme; some sources have a
catalogue and most do not.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from src.domain.assurance.obligation_citation import ReferenceProvisions, source_key
from src.domain.yaml_documents import parse_yaml

logger = logging.getLogger(__name__)

_BUNDLED_VOCAB_DIR = Path(__file__).parent.parent.parent / "ontologies" / "assurance" / "reference_vocab"


@lru_cache(maxsize=32)
def _load_vocab(path: Path) -> dict[str, object]:
    try:
        with open(path) as fh:
            data = parse_yaml(fh)
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


#: The section of a vocabulary that lists what an obligation can cite. The other sections hold
#: classification values (an integrity level, a threat category), which nothing is obliged *by*.
_PROVISIONS_SECTION = "key_clauses"
#: Other ways the vocabulary's subject is written, where its file name is not how it is cited.
_ALSO_CITED_AS = "also_cited_as"


def provisions_by_source(*, repo_root: Path | None = None) -> ReferenceProvisions:
    """What each vocabulary lists as citable, keyed the way an obligation's source is compared.

    A vocabulary with no such section is left out rather than entered empty: it describes a
    classification scheme, and entering it would report every provision cited against it as
    unlisted when the truth is that it lists none.
    """
    listed: dict[str, frozenset[str]] = {}
    for scheme in list_schemes(repo_root=repo_root):
        vocab = load_scheme(scheme, repo_root=repo_root)
        section = vocab.get(_PROVISIONS_SECTION)
        if not isinstance(section, dict) or not section:
            continue
        provisions = frozenset(str(provision) for provision in section)
        other_names = vocab.get(_ALSO_CITED_AS)
        names = [scheme, *(other_names if isinstance(other_names, list) else [])]
        listed.update({source_key(str(name)): provisions for name in names})
    return listed
