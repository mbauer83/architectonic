"""A diagram that says it draws a relation must draw it — the other half of E316.

`connection-ids-used` is not bookkeeping. It answers *which views show this connection*, so impact
analysis reads it, and an entry the picture does not contain is a wrong answer about the model rather
than an untidy file.

The rule set had this in one direction only. **E309** refuses an `entity-ids-used` entry whose alias
the body does not declare; **E315/E316/E317** report what the body draws and the frontmatter does not
own. Nothing reported a *listed* connection the body does not draw, so the two sides of the same
disagreement were policed asymmetrically, and the entity side is the one that got the rule.

Where the wrong entry persists rather than self-heals is the reason this is worth a diagnostic. A
regenerating refresh redraws the missing edge, so the claim becomes true again. On a `manual-layout`
diagram the body is kept verbatim and the reference set is unioned, so it never does — and a
hand-edited file never does either.

**Warning, not error.** It is stated over live model content, and a repository that verified clean
must not start failing over frontmatter nobody has touched. The severity says "this claim is wrong",
not "this write is refused" — the same call W045 makes for the same reason.

Silence is not evidence, which is what keeps this from firing on legitimate content: an entry is
reported only where the body positively contradicts it, judged by
`src/domain/diagrams/recorded_references.py` — the same judgement the write path applies when it
decides what survives a body replacement, so a reconcile cannot drop what the verifier would keep.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification._verifier_rules_puml_completeness import (
    check_diagram_relation_completeness,
)
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.infrastructure.artifact_index import shared_artifact_index

ALPHA = "REQ@1000000000.AaaAaa.alpha"
BETA = "REQ@1000000001.BbbBbb.beta"
GAMMA = "REQ@1000000002.CccCcc.gamma"
INFLUENCE = f"{ALPHA}---{BETA}@@archimate-influence"
COMPOSITION = f"{ALPHA}---{GAMMA}@@archimate-composition"


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(artifact_id: str, name: str) -> str:
    prefix, rand = artifact_id.split("@")[0], artifact_id.split(".")[1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-07-29'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {prefix}_{rand}
```
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    req_dir = root / "model" / "motivation" / "requirement"
    for eid, name in ((ALPHA, "Alpha"), (BETA, "Beta"), (GAMMA, "Gamma")):
        _write(req_dir / f"{eid}.md", _entity(eid, name))
    _write(
        req_dir / f"{ALPHA}.outgoing.md",
        f"""\
---
source-entity: {ALPHA}
version: 0.1.0
status: draft
last-updated: '2026-07-29'
---

<!-- §connections -->

### archimate-influence → {BETA}

### archimate-composition → {GAMMA}
""",
    )
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _fm(*, connection_ids: list[str], **extra: object) -> dict:
    fm: dict = {
        "artifact-id": "ARC@1000000009.DiagAa.view",
        "artifact-type": "diagram",
        "diagram-type": "archimate-motivation",
        "entity-ids-used": [ALPHA, BETA, GAMMA],
        "connection-ids-used": connection_ids,
    }
    fm.update(extra)
    return fm


def _declaring(*aliases: str) -> str:
    """A body that declares each alias and draws nothing between them."""
    return "".join(f'rectangle "x" <<requirement>> as {alias}\n' for alias in aliases)


def _issues(repo: Path, body: str, fm: dict) -> list:
    registry = ArtifactRegistry(shared_artifact_index(repo))
    result = VerificationResult(
        path=repo / "diagram-catalog" / "diagrams" / "view.puml", file_type="diagram"
    )
    check_diagram_relation_completeness(
        body, fm, registry, result, "view.puml",
        stereotype_map=_catalogs().ontology.archimate_stereotype_to_connection_type(),
        diagram_type_catalog=_catalogs().diagram_types,
    )
    return result.issues


def _codes(issues: list) -> list[str]:
    return [i.code for i in issues]


class TestAListedConnectionTheBodyDoesNotDraw:
    def test_it_is_reported(self, repo: Path) -> None:
        """Both endpoints declared, no relation between them: the body had the vocabulary to draw
        the influence and did not, so the claim is contradicted rather than merely unconfirmed."""
        issues = _issues(repo, _declaring("REQ_AaaAaa", "REQ_BbbBbb"), _fm(connection_ids=[INFLUENCE]))

        assert _codes(issues) == ["W307"]

    def test_the_message_names_the_reference(self, repo: Path) -> None:
        """A finding that does not say which entry is wrong cannot be acted on."""
        issues = _issues(repo, _declaring("REQ_AaaAaa", "REQ_BbbBbb"), _fm(connection_ids=[INFLUENCE]))

        assert INFLUENCE in issues[0].message

    def test_it_is_a_warning(self, repo: Path) -> None:
        """Stated over live model content, so it must not turn a clean repository red."""
        issues = _issues(repo, _declaring("REQ_AaaAaa", "REQ_BbbBbb"), _fm(connection_ids=[INFLUENCE]))

        assert issues[0].severity == Severity.WARNING

    def test_each_wrong_entry_is_reported_once(self, repo: Path) -> None:
        body = _declaring("REQ_AaaAaa", "REQ_BbbBbb", "REQ_CccCcc")
        issues = _issues(repo, body, _fm(connection_ids=[INFLUENCE, COMPOSITION, INFLUENCE]))

        assert _codes(issues) == ["W307", "W307"]


class TestWhatIsNotContradicted:
    def test_a_drawn_relation_raises_nothing(self, repo: Path) -> None:
        assert _issues(repo, "REQ_AaaAaa ..> REQ_BbbBbb\n", _fm(connection_ids=[INFLUENCE])) == []

    def test_an_endpoint_the_body_never_declares_is_not_contradicted(self, repo: Path) -> None:
        """The body could not have drawn it, so its absence says nothing. This is the half that
        keeps the rule off diagrams that legitimately list more than they show."""
        assert _issues(repo, _declaring("REQ_AaaAaa"), _fm(connection_ids=[INFLUENCE])) == []

    def test_the_short_id_form_counts_as_drawn(self, repo: Path) -> None:
        """`connection-ids-used` may carry the slug-free form; comparison is through stable ids."""
        short = "REQ@1000000000.AaaAaa---REQ@1000000001.BbbBbb@@archimate-influence"
        assert _issues(repo, "REQ_AaaAaa ..> REQ_BbbBbb\n", _fm(connection_ids=[short])) == []

    def test_a_relation_drawn_as_nesting_counts_as_drawn(self, repo: Path) -> None:
        """Composition is drawn by nesting one box in another, with no arrow at all."""
        body = (
            'rectangle "Alpha" <<requirement>> as REQ_AaaAaa {\n'
            '  rectangle "Gamma" <<requirement>> as REQ_CccCcc\n'
            "}\n"
        )
        assert _issues(repo, body, _fm(connection_ids=[COMPOSITION])) == []

    def test_a_relation_drawn_as_indirect_nesting_counts_as_drawn(self, repo: Path) -> None:
        """Two levels down states the outer pair too, which is why `indirect_nesting_relations`
        exists — reading one level would report this correct entry as wrong."""
        body = (
            'rectangle "Alpha" <<requirement>> as REQ_AaaAaa {\n'
            '  rectangle "Beta" <<requirement>> as REQ_BbbBbb {\n'
            '    rectangle "Gamma" <<requirement>> as REQ_CccCcc\n'
            "  }\n"
            "}\n"
        )
        # INFLUENCE is listed too, so E316 has nothing to say about the A-B level and the
        # assertion is about W307 alone.
        assert _codes(_issues(repo, body, _fm(connection_ids=[COMPOSITION, INFLUENCE]))) == []

    def test_an_unreadable_id_is_left_to_the_rule_that_owns_it(self, repo: Path) -> None:
        """A malformed reference is E301's finding, not a claim about the picture."""
        body = _declaring("REQ_AaaAaa", "REQ_BbbBbb")
        assert _codes(_issues(repo, body, _fm(connection_ids=["not-a-connection-id"]))) == []

    def test_an_undecided_pair_is_not_contradicted(self, repo: Path) -> None:
        """A bare arrow between a pair joined by two connections names neither. Reporting the one
        that is not listed would be reading silence as evidence — the same restraint the write-path
        reconcile applies to the same pair."""
        second = f"{ALPHA}---{BETA}@@archimate-association"
        _write(
            repo / "model" / "motivation" / "requirement" / f"{ALPHA}.outgoing.md",
            f"""\
---
source-entity: {ALPHA}
version: 0.1.0
status: draft
last-updated: '2026-07-29'
---

<!-- §connections -->

### archimate-influence → {BETA}

### archimate-association → {BETA}

### archimate-composition → {GAMMA}
""",
        )
        issues = _issues(repo, "REQ_AaaAaa --> REQ_BbbBbb\n", _fm(connection_ids=[INFLUENCE, second]))

        assert _codes(issues) == []


class TestScope:
    def test_a_diagram_that_owns_its_entities_is_out_of_scope(self, repo: Path) -> None:
        """A sequence body speaks its own vocabulary; the shared relation parser cannot read it, so
        anything this rule concluded there would be an artefact of not understanding the body."""
        fm = _fm(connection_ids=[INFLUENCE], **{"diagram-type": "sequence"})
        assert _issues(repo, _declaring("REQ_AaaAaa", "REQ_BbbBbb"), fm) == []

    def test_a_standalone_diagram_is_out_of_scope(self, repo: Path) -> None:
        fm = _fm(
            connection_ids=[INFLUENCE],
            **{"diagram-entities": {"box": [{"id": "b1"}]}},
        )
        assert _issues(repo, _declaring("REQ_AaaAaa", "REQ_BbbBbb"), fm) == []
