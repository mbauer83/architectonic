"""Verifier rule: dangling edge-label override detection."""

from __future__ import annotations

import re

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult


def check_edge_label_overrides(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    """Flag edge-labels overrides whose alias pair no longer appears in the rendered PUML."""
    raw = fm.get("edge-labels")
    if not isinstance(raw, dict) or not raw:
        return

    _conn_line_re = re.compile(r"^\s*([\w-]+)\s+[-.*|o<>][^\n:]*?[-.*|o<>]\s+([\w-]+)", re.MULTILINE)
    rendered_pairs: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("'") or "[hidden]" in stripped:
            continue
        m = _conn_line_re.match(line)
        if m:
            rendered_pairs.add(f"{m.group(1)}:{m.group(2)}")

    for key in raw:
        if key not in rendered_pairs:
            result.issues.append(Issue(
                Severity.ERROR,
                "E410",
                f"edge-labels key '{key}' does not match any rendered connection (dangling override)",
                loc,
            ))
