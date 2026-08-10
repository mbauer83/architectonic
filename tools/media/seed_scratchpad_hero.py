"""Seed the demo workspace the README's scratchpad picture is taken from.

The shot needs something a scratchpad honestly looks like mid-thought: a couple of dozen notes,
most of them undecided, a few narrowed, two bound to elements that already exist, and one that has
been **lifted** and so carries a realization. The last of those cannot be faked — a realized note
names an entity a lift created, and writing one by hand would put a reference to nothing into a
file that claims otherwise.

It also cannot be produced in *this* repository without leaving an entity behind that exists only
to be photographed. So the picture comes from a **separate, disposable workspace**, and this script
is what makes it reproducible: run it against a freshly initialised instance and the fixture is the
same one every time, down to the ids being the only thing that differs.

    mkdir -p ~/architectonic-hero/{engagements/ENG-DEMO/architecture-repository,enterprise-repository}
    # …arch-workspace.yaml naming both as `local:`, `git init` in each, then:
    arch-init --initialize-engagement-repo-if-empty --initialize-enterprise-repo-if-empty
    arch-backend --daemon --port 8377
    python tools/media/seed_scratchpad_hero.py --base http://localhost:8377
    # then, from tools/gui:
    E2E_BASE_URL=http://localhost:8377 npx playwright test --project=media tests/media/scratchpadMedia.spec.ts

The frames are deliberately shorter than the seeded default (340 rather than 600), so **two of them
fit on screen at once**. A shot of one frame cannot show a link crossing between frames, and those
links are the whole argument for one canvas rather than four tabs.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

#: Two rows per frame, so each frame reads as a working surface rather than as a margin.
NOTES: tuple[tuple[str, str, dict[str, object], tuple[int, int]], ...] = (
    # ── Vision & strategy ────────────────────────────────────────────────────
    ("n1", "Customers abandon signup at the identity check", {}, (40, 60)),
    ("n2", "Regulatory pressure on KYC", {"bind": "driver"}, (270, 60)),
    ("n3", "Onboarding feels like paperwork", {"domain": "motivation"}, (500, 60)),
    ("n4", "Reduce time to first payment", {"type": "goal"}, (730, 60)),
    ("n5", "Trust is the product, not a feature", {}, (960, 60)),
    ("n6", "Verify identity in under two minutes", {"type": "requirement"}, (155, 190)),
    ("n7", "Compliance sign-off is the bottleneck", {}, (385, 190)),
    ("n8", "Fewer manual reviews", {"type": "outcome"}, (615, 190)),
    # Lifted below, which is what makes it the one realized note on the canvas.
    ("n9", "Self-serve for low-risk customers", {"type": "goal"}, (845, 190)),
    # ── Portfolio ────────────────────────────────────────────────────────────
    ("n10", "Customer onboarding", {"bind": "capability"}, (90, 440)),
    ("n11", "Payments platform", {"bind": "capability"}, (370, 440)),
    ("n12", "Q3 — identity rework", {"domain": "strategy"}, (650, 440)),
    ("n13", "Who owns the risk model?", {}, (930, 440)),
    ("n14", "Shared identity service, or one per product?", {}, (230, 570)),
    ("n15", "Sequence the rework behind the KYC deadline", {"domain": "strategy"}, (510, 570)),
    ("n16", "Budget sits with shared services", {}, (790, 570)),
)

#: The last three cross frames, which is the picture's point.
LINKS: tuple[tuple[str, str, str], ...] = (
    ("l1", "n1", "n3"), ("l2", "n2", "n7"), ("l3", "n3", "n4"), ("l4", "n6", "n4"),
    ("l5", "n8", "n4"), ("l6", "n7", "n8"), ("l7", "n5", "n1"), ("l8", "n9", "n8"),
    ("l12", "n14", "n10"), ("l13", "n15", "n12"), ("l14", "n16", "n11"),
    ("l9", "n4", "n10"), ("l10", "n9", "n12"), ("l11", "n6", "n11"),
)

AREAS = {
    "strategy": [0, 0, 1200, 340],
    "portfolio": [0, 380, 1200, 340],
    "project": [0, 760, 1200, 340],
    "enabling": [0, 1140, 1200, 340],
}

#: Bound notes need something that already exists, so the model gets these first.
SEED_ENTITIES = (
    ("capability", "Customer onboarding"),
    ("capability", "Payments platform"),
    ("driver", "Regulatory pressure on KYC"),
)


def call(base: str, method: str, path: str, body: object | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base}{path}", data=data, method=method, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(request) as response:  # noqa: S310 — a localhost backend the caller named
        return json.loads(response.read() or b"{}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8377")
    parser.add_argument("--name", default="Onboarding rework")
    arguments = parser.parse_args()
    base = arguments.base.rstrip("/")

    created: dict[str, str] = {}
    for artifact_type, name in SEED_ENTITIES:
        answer = call(base, "POST", "/api/entities", {
            "artifact_type": artifact_type, "name": name, "dry_run": False,
            "summary": "Seeded so the scratchpad has something real to bind to.",
        })
        # `artifact_id`, not `artifact-id`: the entity write answers in snake_case while the
        # scratchpad routes answer in the document's kebab-case. Two vocabularies, one client.
        created[name] = answer["artifact_id"]

    scratchpad = call(base, "POST", "/api/scratchpads", {"name": arguments.name})
    identifier = urllib.parse.quote(scratchpad["artifact-id"], safe="")

    def note_body(note_id: str, title: str, shape: dict[str, object]) -> dict[str, object]:
        if "bind" in shape:
            return {
                "id": note_id, "title": title, "destination": "element",
                "element-type": shape["bind"],
                "model-ref": {"artifact-id": created[title], "kind": "bound"},
            }
        if "type" in shape:
            return {"id": note_id, "title": title, "destination": "element", "element-type": shape["type"]}
        if "domain" in shape:
            return {"id": note_id, "title": title, "destination": "element", "domain": shape["domain"]}
        return {"id": note_id, "title": title}

    filled = call(base, "PATCH", f"/api/scratchpads/{identifier}", {
        "version": scratchpad["version"],
        "upsert": {
            "notes": [note_body(nid, title, shape) for nid, title, shape, _ in NOTES],
            "links": [{"id": lid, "source": s, "target": t} for lid, s, t in LINKS],
        },
        "layout": {"notes": {nid: list(at) for nid, _, _, at in NOTES}, "areas": AREAS},
    })

    # One real lift, so one note is genuinely realized rather than described as one.
    lifted = call(base, "POST", f"/api/scratchpads/{identifier}/lift", {
        "version": filled["version"], "selection": ["n9"], "targets": {},
        "draw": False, "dry-run": False,
    })
    if not lifted.get("committed"):
        raise SystemExit(f"the lift did not commit: {lifted.get('refusal') or lifted}")

    print(scratchpad["artifact-id"])


if __name__ == "__main__":
    main()
