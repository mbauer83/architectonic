"""Why the router is on `vue-router` 4, and what would make 5 worth taking.

Like the TypeScript refusal beside it, this is a decision written so it **fails when its own reason
stops holding**, rather than a paragraph someone would have to think to re-read.

**What was measured 2026-09-01**, with `vue-router` 5.3.0 installed and every gate run:

* It works. Typecheck across all three tsconfigs, build, `contracts:check` and the 2,046 unit tests
  all pass; the four things this application imports — `useRoute`, `useRouter`, `RouterLink`,
  `onBeforeRouteLeave` — are unchanged.
* It is not a router any more, as far as a dependency closure is concerned. 5.x moves its build-time
  integrations into runtime `dependencies`: `unplugin`, `chokidar`, `@vue-macros/common`,
  `@vue/devtools-kit` and eleven more. `unplugin` in turn declares optional peers on every bundler
  there is — `webpack`, `@rspack/core`, `@farmfe/core`, `esbuild`, `rollup`, `rolldown`, `vite`,
  `unloader` — and the production closure follows them.
* So the **conveyed** set, which is what a licence obligation attaches to, goes from **57 components
  to 144**, and 44 of the arrivals report no licence at all. The licence gate fails on them, which is
  the second, independent control saying the same thing.

The product needs nothing from 5. Taking it would mean either shipping a notices file that describes
four bundlers the product does not convey, or changing what the licence gate counts as production —
a supply-chain governance decision that should be taken on its own terms and not inside a router
upgrade.

**Reopening triggers.** Either of these makes the question live again:

1. `vue-router` moving its build-time integrations out of runtime `dependencies` — check with
   ``npm view vue-router dependencies``.
2. A decision about whether the npm production closure should follow optional peer dependencies at
   all. That is `tools/licensing/check_licenses.py`'s `collect_npm`, and it is the reason the 144 is
   what it is.
"""

from __future__ import annotations

import json
from pathlib import Path

_GUI = Path(__file__).resolve().parents[2] / "tools" / "gui"


def test_the_router_is_still_declared_on_four() -> None:
    declared = json.loads((_GUI / "package.json").read_text(encoding="utf-8"))
    router = declared["dependencies"]["vue-router"]
    assert router.lstrip("^~>=< ").startswith("4."), (
        f"`vue-router` is declared as {router!r}. If 5 was taken deliberately, this module is the "
        "refusal it supersedes — replace it with what the new arrangement guarantees, and say what "
        "happened to the 87 production components its dependency graph brings with it."
    )


def test_the_production_closure_is_the_one_the_notices_describe() -> None:
    """The independent half: whatever is inventoried is what `THIRD-PARTY-NOTICES.md` claims.

    Stated as an agreement rather than as a number, because the inventory moves whenever a real
    dependency does. What it must never do is describe a set nobody assembled.
    """
    inventory = json.loads((_GUI.parents[1] / "licenses" / "npm.json").read_text(encoding="utf-8"))
    assert inventory["ecosystem"] == "npm"
    assert inventory["count"] == len(inventory["components"])
    assert all(component["bucket"] != "unknown" for component in inventory["components"]), sorted(
        c["name"] for c in inventory["components"] if c["bucket"] == "unknown"
    )
