#!/usr/bin/env python
"""Generate THIRD-PARTY-NOTICES.md from the committed license inventories.

Reads ``licenses/{python,npm,native}.json`` (produced by check_licenses.py + the
curated native list) and renders a single top-level notices file: the project's
own license, the corresponding-source offers for every copyleft / weak-copyleft
bundled or invoked component (GPL/LGPL/EPL/MPL — the legally load-bearing part),
and the full permissive inventory per ecosystem.

Usage:
    generate-notices --write    # regenerate THIRD-PARTY-NOTICES.md
    generate-notices --check    # CI: fail if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licenses"
NOTICES_PATH = REPO_ROOT / "THIRD-PARTY-NOTICES.md"

# Corresponding-source pointers for non-native copyleft/weak-copyleft components
# (native components carry their own source_url/obligation in native.json).
_SOURCE_OFFERS: dict[str, dict[str, str]] = {
    "cvss": {
        "source_url": "https://github.com/RedHatProductSecurity/cvss",
        "license_text": "licenses/texts/LGPL-3.0-or-later.txt + licenses/texts/GPL-3.0-or-later.txt",
        "obligation": (
            "Not conveyed by this project: it is a declared dependency that pip/uv installs from "
            "PyPI, so upstream is the distributor. Nothing is vendored and nothing is statically "
            "combined — cvss is an ordinary runtime import from site-packages, replaceable with a "
            "modified build by `pip install` alone. LGPLv3 §4's duties fall on whoever conveys a "
            "work containing the library; a redistributor who vendors or bundles it takes those "
            "on, including §4(a)-(b) notice and license texts."
        ),
    },
}

_COPYLEFT_MARKERS = ("gpl", "lgpl", "epl", "mpl", "mozilla", "eclipse", "lesser general", "general public")


def _load(ecosystem: str) -> dict:
    path = LICENSES_DIR / f"{ecosystem}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def missing_license_texts() -> list[str]:
    """Every `license_text` path an entry points at that is not actually in the tree.

    A notice that cites a text it does not ship discharges nothing, and the failure is silent:
    the generated file looks complete. Checked here so `--check` fails on it in CI.
    """
    declared: list[str] = []
    for ecosystem in ("python", "npm", "native"):
        for comp in _load(ecosystem)["components"]:
            declared.append(str(comp.get("license_text") or ""))
    declared.extend(str(offer.get("license_text") or "") for offer in _SOURCE_OFFERS.values())
    missing: list[str] = []
    for entry in declared:
        # A component may need several texts (a license plus its exception).
        for rel in (part.strip() for part in entry.split("+") if part.strip()):
            if not (REPO_ROOT / rel).is_file():
                missing.append(rel)
    return sorted(set(missing))


def _is_copyleft(license_text: str) -> bool:
    return any(m in license_text.lower() for m in _COPYLEFT_MARKERS)


def _project_license_line() -> str:
    text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    return text.splitlines()[0].strip() if text.strip() else "MIT License"


def _render() -> str:
    python = _load("python")
    npm = _load("npm")
    native = _load("native")

    lines: list[str] = []
    lines.append("# Third-Party Notices")
    lines.append("")
    lines.append(
        "Architectonic is distributed under the "
        f"**{_project_license_line()}** (see `LICENSE`). Installing or building it assembles the "
        "third-party components listed below, each under its own license — this file inventories "
        "them and their terms. This file is generated "
        "by `tools/licensing/generate_notices.py` from the committed inventories in `licenses/`; regenerate "
        "with `--write` after any dependency change. Not legal advice."
    )
    lines.append("")

    # ── Copyleft / weak-copyleft: corresponding-source offers (load-bearing) ──
    lines.append("## Copyleft and weak-copyleft components")
    lines.append("")
    lines.append(
        "**This project distributes source and a build recipe — it conveys none of the binaries "
        "below.** Each arrives from its own upstream on the machine that builds: the Debian "
        "packages via `apt-get` during `docker build`, the PlantUML jar from Maven Central via "
        "`get-plantuml`, the Python library from PyPI via pip/uv. Those upstreams are the "
        "distributors, and each discharges its own source duty. No corresponding-source "
        "obligation therefore arises for Architectonic."
    )
    lines.append("")
    lines.append(
        "What follows is a disclosure inventory, for two purposes: to say what a build assembles "
        "and under what terms, and to say what becomes YOUR obligation if you redistribute the "
        "result — see the closing section. None of these licenses reaches Architectonic's own "
        "code, but the reason differs per component (separate-process execution, mere aggregation "
        "in an image, an unmodified runtime import), so each states its own. Verbatim license "
        "texts are in `licenses/texts/`."
    )
    lines.append("")
    for comp in native["components"]:
        if comp.get("obligation") and _is_copyleft(comp["license"]):
            lines.append(f"### {comp['name']} — {comp['license']}")
            lines.append(f"- Version: {comp['version']}")
            lines.append(f"- Exposure: {comp['exposure']}")
            lines.append(f"- Source: {comp['source_url']}")
            if comp.get("license_text"):
                lines.append(f"- License text: {comp['license_text']}")
            lines.append(f"- Obligation: {comp['obligation']}")
            lines.append("")
    for comp in python["components"] + npm["components"]:
        if _is_copyleft(comp["license"]) and comp["name"] in _SOURCE_OFFERS:
            offer = _SOURCE_OFFERS[comp["name"]]
            lines.append(f"### {comp['name']} — {comp['license']}")
            lines.append(f"- Version: {comp['version']}")
            lines.append(f"- Source: {offer['source_url']}")
            if offer.get("license_text"):
                lines.append(f"- License text: {offer['license_text']}")
            lines.append(f"- Obligation: {offer['obligation']}")
            lines.append("")

    # ── Full permissive inventory ──
    for title, data in (
        ("Python dependencies", python),
        ("Frontend (npm) dependencies", npm),
        ("Native / system runtime components", native),
    ):
        lines.append(f"## {title} ({data['count']})")
        lines.append("")
        lines.append("| Component | Version | License |")
        lines.append("|---|---|---|")
        for comp in data["components"]:
            lines.append(f"| {comp['name']} | {comp['version'] or '—'} | {comp['license']} |")
        lines.append("")

    lines.extend(_redistributor_lines())

    return "\n".join(lines) + "\n"


def _redistributor_lines() -> list[str]:
    """What publishing a BUILT image means — kept in proportion.

    Shipping unmodified distro packages in an image is ordinary practice and low-risk, and saying
    so plainly is more useful than reciting §3 at someone. The section's job is to mark the line
    where it stops being ordinary: modifying a copyleft component, or compiling against one.
    """
    return [
        "## If you publish a built image",
        "",
        "Nothing above obliges Architectonic, which conveys no binaries. If you push a built image "
        "somewhere, you do convey them — but for this image that is **ordinary, low-risk practice**, "
        "and the reason is worth stating rather than assuming: every copyleft component in it is an "
        "**unmodified upstream package** whose exact version is identifiable from the image, and "
        "whose corresponding source is permanently retrievable from the Debian archive "
        "(`apt-get source`, snapshot.debian.org) or Maven Central. The substance of the "
        "source-availability terms is satisfied in fact — a recipient who wants the source can get "
        "precisely the source that built those binaries.",
        "",
        "The formality is thinner than the substance: GPL-2.0 §3 lists three discharges (source "
        "alongside, a written offer valid three years, or passing along an offer received — the "
        "last only for noncommercial distribution), and a link to Debian is strictly none of them. "
        "GPL-3.0 §6(d) explicitly permits the third-party-server route that GPL-2.0 predates. That "
        "gap is why countless open-source images ship exactly as this one does and it has never "
        "been anyone's problem: enforcement concerns **withheld** source, not source that is one "
        "well-known command away.",
        "",
        "Where it stops being ordinary — the cases actually worth attention:",
        "",
        "- **You modify a copyleft component** (patch git, rebuild Graphviz, repackage the jar). "
        "Then the pointer upstream is genuinely insufficient: the corresponding source is now "
        "*yours*, and you must supply it.",
        "- **You compile or link against one** rather than invoking it as a separate process. The "
        "separate-process reasoning in the entries above is what keeps this project's own code out "
        "of scope; static combination would change the answer.",
        "- **A customer or procurement process asks formally** — for a written offer, a signed "
        "SBOM, or an audit. That is a commercial requirement rather than a legal shift, but it is "
        "the situation in which a formal offer earns its keep.",
        "",
        "Cheap hygiene that keeps you in the easy case: leave the copyleft packages unmodified, pin "
        "the base image by digest so the exact source versions stay identifiable, and keep this "
        "file and `licenses/texts/` in the image (the Dockerfile already does — the Debian packages "
        "also carry their own texts under `/usr/share/doc/*/copyright`).",
        "",
    ]

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate THIRD-PARTY-NOTICES.md")
    mode.add_argument("--check", action="store_true", help="CI: fail if the committed file is stale")
    args = parser.parse_args(argv)

    rendered = _render()
    if args.write:
        if missing := missing_license_texts():
            print("refusing to write: license texts cited but not present: " + ", ".join(missing))
            return 1
        NOTICES_PATH.write_text(rendered, encoding="utf-8")
        print(f"wrote {NOTICES_PATH.relative_to(REPO_ROOT)}")
        return 0
    if not NOTICES_PATH.exists():
        print(f"missing {NOTICES_PATH.name} — run generate-notices --write")
        return 1
    if missing := missing_license_texts():
        print("license texts cited by the inventories but not present: " + ", ".join(missing))
        return 1
    if NOTICES_PATH.read_text(encoding="utf-8") != rendered:
        print(f"{NOTICES_PATH.name} is stale — run generate-notices --write and commit")
        return 1
    print(f"{NOTICES_PATH.name} is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
