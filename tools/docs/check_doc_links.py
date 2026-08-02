"""Documentation link checker.

Contract (exit non-zero on any violation):
- every relative Markdown link/image target in the checked set resolves to an existing file;
- every Markdown image has non-empty, descriptive alt text;
- every intra-docs anchor (``page.md#heading`` and in-page ``#heading``) resolves to a real
  heading in the target file (GitHub slugification);
- every file under ``docs/media/`` is referenced by at least one checked file (no orphans).

External URLs (``http(s)://``, ``mailto:``) are not fetched — network checks are out of
scope for CI determinism.

Usage:
    uv run python tools/docs/check_doc_links.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
CHECKED_FILES = sorted(DOCS.rglob("*.md")) + [REPO_ROOT / "README.md"]

_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_MEDIA_COMMENT_RE = re.compile(r"<!--\s*media:\s*([^\s—-]+(?:[^\s]*)?)")


def _slugify(heading: str) -> str:
    """GitHub-style heading slug: strip markup, lowercase, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip())
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def _anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        slugs: set[str] = set()
        counts: dict[str, int] = {}
        for match in _HEADING_RE.finditer(path.read_text(encoding="utf-8")):
            base = _slugify(match.group(1))
            n = counts.get(base, 0)
            counts[base] = n + 1
            slugs.add(base if n == 0 else f"{base}-{n}")
        cache[path] = slugs
    return cache[path]


def _check_file(md: Path, anchor_cache: dict[Path, set[str]], referenced: set[Path]) -> list[str]:
    errors: list[str] = []
    text = md.read_text(encoding="utf-8")
    rel = md.relative_to(REPO_ROOT)

    generic_alt_text = {"diagram", "figure", "image", "photo", "screenshot"}
    for match in _IMAGE_RE.finditer(text):
        alt_text = match.group(1).strip()
        if not alt_text or alt_text.casefold() in generic_alt_text:
            errors.append(f"{rel}: image needs meaningful alt text -> {match.group(2)}")

    for match in _MEDIA_COMMENT_RE.finditer(text):
        for token in match.group(1).split("·"):
            candidate = (REPO_ROOT / token.strip()).resolve()
            if candidate.is_file():
                referenced.add(candidate)

    for match in _LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        resolved = (md.parent / path_part).resolve() if path_part else md
        if not resolved.exists():
            errors.append(f"{rel}: broken link -> {target}")
            continue
        referenced.add(resolved)
        if anchor and resolved.suffix == ".md" and anchor not in _anchors_of(resolved, anchor_cache):
            errors.append(f"{rel}: missing anchor -> {target}")
    return errors


def main(argv: list[str]) -> int:
    """Takes no arguments, and says so rather than running the check on `--help`."""
    argparse.ArgumentParser(prog="check_doc_links.py", description=__doc__).parse_args(argv[1:])
    anchor_cache: dict[Path, set[str]] = {}
    referenced: set[Path] = set()
    errors: list[str] = []

    for md in CHECKED_FILES:
        errors.extend(_check_file(md, anchor_cache, referenced))

    media_dir = DOCS / "media"
    if media_dir.is_dir():
        orphans = [
            f for f in sorted(media_dir.iterdir())
            if f.is_file() and f.name != "manifest.json" and f.resolve() not in referenced
        ]
        errors.extend(
            f"docs/media/{f.name}: orphaned media file (referenced from no checked document)"
            for f in orphans
        )

    if errors:
        print(f"check_doc_links: {len(errors)} violation(s)")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"check_doc_links: OK ({len(CHECKED_FILES)} files, {len(referenced)} referenced targets)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
