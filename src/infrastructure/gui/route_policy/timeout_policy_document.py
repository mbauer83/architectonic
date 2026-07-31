"""The frontend's timeout-policy document, derived from the manifest.

The classification is decided in the route-policy manifest, and two frontend consumers need it —
the HTTP client and the Vite dev config. Those live in different TypeScript programs, so no module
can be shared between them, and each reading the same JSON through its own derivation would put two
copies of one algorithm in a place nothing could compare.

So the derivation happens here, once, in the language that owns the manifest, and the document
carries its *results*: the budgets, and the ordered regular expressions the dev proxy uses as
context keys. Both TypeScript consumers then only read. A fitness function regenerates this and
compares, the same way the generated OpenAPI types are checked.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.infrastructure.gui.route_policy._pending import LEGACY_ROUTES
from src.infrastructure.gui.route_policy._types import RouteRow

#: Client abort budget per class, in milliseconds. ``None`` means never abort.
BUDGET_MS: dict[str, int | None] = {"default": 10_000, "derived-graph": 60_000, "streaming": None}

#: How much longer the dev proxy waits than the client. The client's own abort has to fire first:
#: it produces a typed timeout the UI can explain, where a proxy that gives up first produces
#: ``ERR_EMPTY_RESPONSE`` and looks like a crashed backend.
PROXY_HEADROOM_MS = 5_000

NON_DEFAULT_CLASSES = ("streaming", "derived-graph")

_PARAM = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")


def template_pattern(template: str) -> str:
    """A route template as a regular expression matching exactly that route.

    Anchored at the front and terminated by the query separator or end of input, never by ``$``
    alone: a dev proxy matches against the request URL, which carries the query string, so a ``$``
    anchor would fail on every request that has one.
    """
    segments = [
        "[^/?#]+" if _PARAM.match(segment) else re.escape(segment)
        for segment in template.split("/")
    ]
    return "^" + "/".join(segments) + r"(\?|$)"


def _templates_for(rows: tuple[RouteRow, ...], timeout_class: str) -> list[str]:
    return sorted(row.template for row in rows if row.timeout_class == timeout_class)


def _legacy_templates_for(rows: tuple[RouteRow, ...], timeout_class: str) -> list[str]:
    """Retired templates still mounted, and the class they keep until their rename lands.

    Taken over every method still on that path, because a proxy matches a URL and cannot see the
    method: a template whose write is long-running lends its budget to its read too.
    """
    by_operation = {row.operation_id: row for row in rows}
    return sorted(
        {
            template
            for (_method, template), operation_id in LEGACY_ROUTES.items()
            if by_operation[operation_id].timeout_class == timeout_class
        }
    )


def _ordered_contexts(templates: list[str]) -> list[str]:
    """Patterns most specific first: Vite uses the first key that matches, so a longer template
    has to be offered before a shorter one it extends."""
    ordered = sorted(templates, key=lambda t: (-t.count("/"), -len(t), t))
    return [template_pattern(template) for template in ordered]


def timeout_policy_document(rows: tuple[RouteRow, ...]) -> dict[str, Any]:
    """The whole document, ready to serialize."""
    templates = {cls: _templates_for(rows, cls) for cls in NON_DEFAULT_CLASSES}
    legacy = {cls: _legacy_templates_for(rows, cls) for cls in NON_DEFAULT_CLASSES}
    return {
        "$comment": (
            "Generated from the REST route-policy manifest by "
            "src/infrastructure/gui/route_policy/timeout_policy_document.py. Do not edit. Both "
            "frontend consumers — the HTTP client and the Vite dev config — read this document "
            "rather than deriving anything, because they live in different TypeScript programs "
            "and a shared module can only be owned by one of them."
        ),
        "budgetMs": BUDGET_MS,
        "proxyHeadroomMs": PROXY_HEADROOM_MS,
        "templates": templates,
        "legacyTemplates": legacy,
        "proxyContexts": {
            cls: _ordered_contexts([*templates[cls], *legacy[cls]]) for cls in NON_DEFAULT_CLASSES
        },
    }


def serialize(rows: tuple[RouteRow, ...]) -> str:
    return json.dumps(timeout_policy_document(rows), indent=2) + "\n"
