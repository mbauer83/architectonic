"""This repository's own model carries every default schema the product ships.

The engagement repository here *is* the dogfood: it is what the demo renders, what the browser suite
drives and what the docs screenshot. A shipped default missing from it means the product's own
showcase is running on a stale configuration, and nothing said so.

**It had been for some time.** The product ships 27 default schemata and this repository held 19 —
the eight attribute and connection-metadata schemata added with
`repo_default_attribute_schemata.py` were never written into it. `arch-repair upgrade` reported them
the moment it was asked, because ensuring them is exactly what its `default-schemata-ensure` step is
for; nobody had asked, and no gate had either.

**It was not harmless.** A browser test asserted that the `service` specialization renders "seven
effective attributes" and passed — because the eighth lives in the missing
`attributes.service.schema.json`. The test was measuring this repository's staleness rather than the
product's behaviour, and it went red the moment the schemata arrived.

**One direction only.** Every shipped default must be present; a repository may hold schemata of its
own beyond them, and authoring one is the product working. So this asserts containment, never
equality, and never a count.

The whole `arch-repair upgrade` detector takes ~27s over this repository, which is too slow to run on
every commit. This asks the one question that is a directory listing, which is the question that
drifted.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.repository.repo_default_schemata import DEFAULT_SCHEMATA

_SCHEMATA = (
    Path(__file__).resolve().parents[2]
    / "engagements" / "ENG-ARCH-REPO" / "architecture-repository" / ".arch-repo" / "schemata"
)


def test_every_shipped_default_schema_is_in_the_self_model() -> None:
    present = {p.name for p in _SCHEMATA.iterdir() if p.suffix == ".json"}
    missing = sorted(set(DEFAULT_SCHEMATA) - present)

    assert missing == [], (
        "the dogfood repository is missing shipped default schemata, so the demo, the browser suite "
        "and the docs figures all run on a stale configuration. Add them with "
        "`uv run arch-repair upgrade --repo-root engagements/ENG-ARCH-REPO/architecture-repository "
        f"--commit` rather than by hand: {missing}"
    )


def test_the_shipped_default_set_is_not_empty() -> None:
    """A guard on the guard: were `DEFAULT_SCHEMATA` to resolve empty, the check above would pass
    over any repository at all, including one holding nothing."""
    assert len(DEFAULT_SCHEMATA) > 10
