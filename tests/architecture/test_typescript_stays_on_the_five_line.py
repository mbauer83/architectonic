"""Why the frontend is on TypeScript 5, and what would make that worth revisiting.

A refusal that lives in prose is a refusal nobody re-reads. This is the same decision written so it
**fails when its own precondition stops holding** — the three reopening triggers below are the three
assertions, and any of them going false is the signal to evaluate the move again rather than to edit
the number here.

**What was measured**, on 2026-09-01, with the toolchain at the versions this release ships:

* `typescript` has a stable 6 line (6.0.2, 6.0.3) and a stable 7 (7.0.2), so "6 does not exist yet"
  is not the reason. `@typescript/typescript6` is real and published.
* Everything in the tree admits 6 except one package. `typescript-eslint` 8.68.0 declares
  `>=4.8.4 <6.1.0`, `vue-tsc` 3.3.11 declares `>=5.0.0`, `ts-api-utils` `>=4.8.4`, `vue` optional.
  `openapi-typescript` 7.13.0 declares `^5.x`, and **every** 7.x release back to 7.7.1 declares the
  same; there is no 8.x line, and `next` points at an older release candidate than `latest`.
* Declaring `typescript@^6.0.3` makes `npm install` fail — `ERESOLVE`, exit 1 — naming that peer.
  npm's own advice is `--force` or `--legacy-peer-deps`, which accept a resolution npm calls
  potentially broken; the enterprise standard refuses that class of escape.
* The dual arrangement was tried, not assumed. `overrides` giving `openapi-typescript` its own
  nested `typescript@5.9.3` **also** fails `ERESOLVE`: npm satisfies a peer from the hoisted install
  and will not nest a second compiler for one. So "one tool stays on 5, everything else moves to 6"
  has no npm-supported spelling here.
* `typescript-eslint`'s upper bound also refuses 7, so 7 is not an escape from the 6 question.

Nothing in the product needs 6, and 5.9.3 is current on the 5 line. So the move costs an escape
hatch and buys nothing, today.

**Re-check by hand with one command**, which is what the assertions below automate::

    node -e 'const l=require("./package-lock.json");
      for (const [p,n] of Object.entries(l.packages))
        if (n.peerDependencies?.typescript) console.log(p, n.version, n.peerDependencies.typescript)'
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_GUI = Path(__file__).resolve().parents[2] / "tools" / "gui"

#: The peer range that blocks the move, exactly as `openapi-typescript` declares it today.
_BLOCKING_PEER = "^5.x"

#: `typescript-eslint`'s range, which admits 6.0 and refuses 7 — so 7 is not a way around 6.
_RULESET_PEER = ">=4.8.4 <6.1.0"


@pytest.fixture(scope="module")
def locked() -> dict[str, dict]:
    return json.loads((_GUI / "package-lock.json").read_text(encoding="utf-8"))["packages"]


def _peer(locked: dict[str, dict], package: str) -> str | None:
    node = locked.get(f"node_modules/{package}", {})
    return node.get("peerDependencies", {}).get("typescript")


def test_the_contract_generator_still_refuses_anything_past_five(locked: dict[str, dict]) -> None:
    """Trigger 1: a release of `openapi-typescript` whose peer admits 6 reopens the whole question."""
    assert _peer(locked, "openapi-typescript") == _BLOCKING_PEER, (
        "`openapi-typescript` no longer declares the peer range that blocked TypeScript 6. "
        "Re-evaluate the move: re-run the one-line peer survey in this module's docstring, then "
        "either take the upgrade or restate the refusal with what is blocking it now."
    )


def test_the_type_aware_ruleset_still_refuses_seven(locked: dict[str, dict]) -> None:
    """Trigger 2: `typescript-eslint` admitting 7 would change which target is even in question."""
    assert _peer(locked, "typescript-eslint") == _RULESET_PEER, (
        "`typescript-eslint`'s TypeScript peer range has moved. The refusal was written against a "
        "ruleset that admits 6.0 and refuses 7; check which targets are now reachable."
    )


def test_the_declared_compiler_is_still_on_the_five_line() -> None:
    """Trigger 3: the state the two triggers above are about. Moving it is the decision itself."""
    declared = json.loads((_GUI / "package.json").read_text(encoding="utf-8"))
    assert declared["devDependencies"]["typescript"].startswith("^5."), (
        "the frontend compiler has left the 5 line. If that was deliberate, this module is the "
        "refusal it supersedes — replace it with what the new arrangement guarantees, including "
        "the guard fixtures that keep a second compiler from silently stopping."
    )
