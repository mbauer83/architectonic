#!/usr/bin/env python
"""Third-party license inventory + CI gate for open-source publication.

Generates a reproducible per-ecosystem license inventory, classifies each
component against the project's own license (MIT), and fails on any denied or
unrecognized license (I-L2). The committed inventory (``licenses/<eco>.json``)
is the drift baseline: ``--check`` regenerates in memory and fails if it differs
or if a new deny/unknown/unacknowledged-review appears.

Usage:
    check-licenses --ecosystem python --write   # regenerate the committed inventory
    check-licenses --ecosystem python --check   # CI gate (no write; fail on drift/deny)
    check-licenses --ecosystem npm --check       # (npm collector; see collect_npm)

Not legal advice: the buckets encode compatibility with MIT redistribution;
ambiguous cases surface as ``review`` and must be acknowledged with a rationale.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licenses"

# Buckets that PASS the gate: allow (permissive) + notice (permissive, must ship
# attribution — every permissive license needs its notice anyway). review and
# deny fail unless the package is acknowledged below. unknown always fails.
_ALLOW = (
    "mit", "bsd", "apache", "isc", "psf", "python-2.0", "python software foundation",
    "mpl", "mozilla public license", "zlib", "0bsd", "unlicense", "cc0", "public domain",
    "wtfpl", "boost", "bsl-1.0",
)
_DENY = ("agpl", "affero")  # strong network copyleft — incompatible with MIT redistribution


def classify(license_text: str) -> str:
    """Map a (possibly messy) license string to a gate bucket."""
    t = license_text.lower()
    if any(k in t for k in _DENY):
        return "deny"
    # LGPL is weak copyleft (dynamic-link/replaceable → compatible with notice); flag for review.
    if "lesser general public" in t or "lgpl" in t:
        return "review"
    # A plain GPL (not LGPL, already handled) would force our code open when combined.
    if "general public license" in t or (("gpl" in t) and ("lgpl" not in t)):
        return "deny"
    if any(k in t for k in _ALLOW):
        return "allow"
    return "unknown"


# Licenses for dependency-closure packages that cannot be introspected on the
# generation platform (e.g. Windows-only deps when generating on Linux). Researched
# from PyPI metadata and recorded so the FULL resolved closure is inventoried rather
# than silently dropped; keeps the gate offline/deterministic (no network at gate time).
_PLATFORM_OVERRIDES: dict[str, str] = {
    "colorama": "BSD-3-Clause",        # PyPI classifier: OSI Approved :: BSD License
    "pywin32": "PSF-2.0",              # PyPI license field 'PSF' + PSF-2.0 classifier
    "pywin32-ctypes": "BSD-3-Clause",  # PyPI license field 'BSD-3-Clause'
}


# Explicitly reviewed, accepted non-``allow`` components: package -> rationale.
# A ``review``/``deny`` bucket for a package listed here does NOT fail the gate.
ACKNOWLEDGED: dict[str, str] = {
    "cvss": (
        "LGPLv3+ (Red Hat CVSS library). Weak copyleft: imported dynamically and "
        "unmodified, and pip-replaceable, so it is compatible with MIT "
        "redistribution provided the LGPL notice + upstream source pointer ship "
        "(THIRD-PARTY-NOTICES). Vetted during the CVSS dependency selection."
    ),
}


def _license_of(dist: object) -> str:
    md = dist.metadata  # type: ignore[attr-defined]
    expr = md.get("License-Expression")
    if expr:
        return str(expr).strip()
    classifiers = [
        c.split("::")[-1].strip()
        for c in md.get_all("Classifier", [])
        if c.startswith("License")
    ]
    if classifiers:
        return "; ".join(sorted(set(classifiers)))
    raw = md.get("License")
    if raw:
        return str(raw).strip().splitlines()[0][:80]
    return "UNKNOWN"


#: ANSI escape sequences, stripped before any tool output is parsed as data.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def collect_python() -> list[dict[str, str]]:
    """Inventory the full SHIPPED runtime closure (non-dev: main + gui + cloud-archive).

    Covers every resolved dependency, including platform-specific ones not installed
    on the generation platform (e.g. the Windows-only pywin32/colorama when generating
    on Linux): their license comes from _PLATFORM_OVERRIDES so the closure is complete
    rather than dropped. Version is read from the lock export (available even when the
    package is not installed locally).
    """
    import importlib.metadata as im

    export = subprocess.run(
        ["uv", "export", "--no-dev", "--group", "gui", "--extra", "cloud-archive",
         "--no-hashes", "--no-emit-project", "--no-annotate"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        # Colour off, deterministically. With it on, an escape sequence reaches stdout and parses as
        # a package named "\x1b" with an UNKNOWN license — which fails this gate for a reason that
        # has nothing to do with licensing, and only on machines where the output is a terminal.
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    ).stdout
    versions: dict[str, str] = {}
    for line in export.splitlines():
        line = _ANSI.sub("", line).strip()
        if not line or line.startswith(("#", "-e", "-")):
            continue
        spec = line.partition(";")[0].strip()
        name, _, version = spec.partition("==")
        name = name.split("[")[0].strip()
        # A requirement line always names a package; anything else is noise from the tool that
        # produced it, and inventing an UNKNOWN-licensed entry from noise is worse than skipping it.
        if not name or not name[0].isalnum():
            continue
        versions.setdefault(name, version.strip())
    rows: list[dict[str, str]] = []
    for name in sorted(versions, key=str.lower):
        try:
            lic = _license_of(im.distribution(name))
        except im.PackageNotFoundError:
            lic = _PLATFORM_OVERRIDES.get(name, "UNKNOWN")
        rows.append({
            "name": name,
            "version": versions[name],
            "license": lic,
            "bucket": classify(lic),
        })
    return rows


def collect_npm() -> list[dict[str, str]]:
    """Inventory the SHIPPED (production) npm set of tools/gui via `npm ls --omit=dev`."""
    gui = REPO_ROOT / "tools" / "gui"
    proc = subprocess.run(
        ["npm", "ls", "--omit=dev", "--all", "--json"],
        cwd=gui, capture_output=True, text=True, check=False,
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )
    data = json.loads(proc.stdout or "{}")
    seen: dict[str, str] = {}

    def walk(deps: dict) -> None:
        for name, node in (deps or {}).items():
            if not isinstance(node, dict):
                continue
            version = str(node.get("version", ""))
            if name not in seen:
                seen[name] = version
            walk(node.get("dependencies", {}))

    walk(data.get("dependencies", {}))
    rows: list[dict[str, str]] = []
    for name in sorted(seen, key=str.lower):
        version = seen[name]
        lic = _npm_license(gui, name, version)
        rows.append({"name": name, "version": version, "license": lic, "bucket": classify(lic)})
    return rows


def _npm_license(gui: Path, name: str, version: str) -> str:
    pkg_json = gui / "node_modules" / name / "package.json"
    try:
        meta = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "UNKNOWN"
    lic = meta.get("license")
    if isinstance(lic, str):
        return lic
    if isinstance(lic, dict):
        return str(lic.get("type", "UNKNOWN"))
    licenses = meta.get("licenses")
    if isinstance(licenses, list) and licenses:
        return " OR ".join(str(x.get("type", "")) for x in licenses if isinstance(x, dict))
    return "UNKNOWN"


_COLLECTORS = {"python": collect_python, "npm": collect_npm}


def _failures(rows: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    for r in rows:
        bucket = r["bucket"]
        if bucket in ("deny", "unknown") and r["name"] not in ACKNOWLEDGED:
            out.append(f"{r['name']} {r['version']}: {bucket} — {r['license']}")
        elif bucket == "review" and r["name"] not in ACKNOWLEDGED:
            out.append(f"{r['name']} {r['version']}: review (unacknowledged) — {r['license']}")
    return out


def _render(ecosystem: str, rows: list[dict[str, str]]) -> str:
    return json.dumps(
        {"ecosystem": ecosystem, "count": len(rows), "components": rows},
        indent=2, sort_keys=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ecosystem", choices=sorted(_COLLECTORS), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the committed inventory")
    mode.add_argument("--check", action="store_true", help="CI gate: fail on drift or deny/unknown/unacked-review")
    args = parser.parse_args(argv)

    rows = _COLLECTORS[args.ecosystem]()
    rendered = _render(args.ecosystem, rows)
    path = LICENSES_DIR / f"{args.ecosystem}.json"
    failures = _failures(rows)

    if args.write:
        LICENSES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)} ({len(rows)} components)")
        if failures:
            print("\nWARNING — unresolved license issues (resolve before committing):")
            for f in failures:
                print(f"  {f}")
            return 1
        return 0

    # --check
    problems: list[str] = list(failures)
    if not path.exists():
        problems.append(f"missing inventory {path.relative_to(REPO_ROOT)} — run --write")
    elif path.read_text(encoding="utf-8") != rendered:
        problems.append(f"{path.relative_to(REPO_ROOT)} is stale — run --write and commit")
    if problems:
        print(f"license gate FAILED ({args.ecosystem}):")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"license gate OK ({args.ecosystem}): {len(rows)} components, no denied/unknown licenses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
