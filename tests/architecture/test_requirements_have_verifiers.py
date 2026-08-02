"""Every requirement something *builds* must be a requirement something *verifies*.

Two days of measurement converged on one structural gap. The chain that answers "does this product
work as intended" is

    requirement  ->  realising component  ->  verifying artefact

and the self-model already carries the first link — `requirements-coverage-gaps` reports it, and
authoring the 21 missing edges took it from 24 gaps to 3. The second link did not exist in any form.
Nothing in the model, and nothing in the suite, said which test verifies which feature. So "have we
omitted anything" could only ever be answered from recollection, which is how a backlog of unknowns
accumulates behind green gates.

**Why the declaration lives in the test and not in the model.** Modelling ~230 test modules as
entities would roughly double the self-model with content about how the product is *built* rather than
what it *is*, and no architect reading the model wants it. The model stays the authority on what the
features *are*, which is the half it is genuinely good at.

**How each option survives drift**, since test files are renamed, split and deleted constantly:

============  ==========================================  =========================================
drift         marker in the test (this)                    entity in the model naming a path
============  ==========================================  =========================================
rename        travels with the file; nothing to update     silently points at nothing
split         stays on whichever half kept it — the        points at whichever half kept the path,
              claim narrows but stays true                 or at neither
delete        requirement re-enters ``_owed()`` and        silently keeps claiming coverage
              **this gate fails**
============  ==========================================  =========================================

So co-location is strictly better on the drift the model option would suffer. The residual risk is the
opposite one and it is real: a marker can outlive the *assertions* that justified it — a test gutted or
rewritten keeps its claim, and no mechanism can tell that the remaining assertions no longer verify the
requirement, because that is a semantic judgement. Three things keep it honest, none of them automatic:

* the marker goes on the **narrowest** test that carries the claim, not on the module, so its scope is
  one or two assertions a reviewer can read;
* a claim is only credible if the test was watched fail without its fix (§1.5), which is the same
  standard the rest of this suite is held to;
* deletion — the common case, and the one drift usually produces — *is* caught, above.

**Why a source scan rather than collected markers.** Under `-n auto` each xdist worker collects a
subset, so no single test can enumerate the suite's markers. Reading the files works everywhere, and
it lets one scan cover all three dialects: a pytest marker, a TypeScript spec's doc tag, and a
harness script's comment. Those are the three kinds of thing that verify something here.

The obligation is deliberately narrow: **active** and **realised**. A `draft` requirement need not be
verified, and neither need one nothing implements yet — demanding otherwise would make authoring a
requirement fail the suite, which is exactly the wrong incentive.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOTS = (REPO_ROOT / "engagements", REPO_ROOT / "enterprise-repository")
#: Where a verification declaration may live: the backend suite, the browser suite, the harnesses.
SCAN_ROOTS = (REPO_ROOT / "tests", REPO_ROOT / "tools")

_REQUIREMENT_FILE = "*motivation/requirement/REQ@*.md"
_ARTIFACT_ID = re.compile(r"^artifact-id:\s*(\S+)", re.MULTILINE)
_STATUS = re.compile(r"^status:\s*(\S+)", re.MULTILINE)
_REALISES = re.compile(r"archimate-realization\s*→\s*(REQ@[\w.\-]+)")

#: The three dialects one declaration takes. A pytest marker so `-m verifies` selects them, and a
#: comment tag for the TypeScript specs and the standalone harnesses, which pytest never collects.
_VERIFIES = re.compile(
    r"""(?:@pytest\.mark\.verifies\(|@verifies\s|verifies:\s*)["'\s]*(REQ@[\w.\-]+)""",
)

#: Excluded from the scan for verification declarations: this file names requirement ids in prose.
_SELF = Path(__file__).name


def _requirement_status() -> dict[str, str]:
    """Every requirement in the model, and its status. The authoritative feature enumeration."""
    found: dict[str, str] = {}
    for root in MODEL_ROOTS:
        for path in root.rglob(_REQUIREMENT_FILE):
            if path.name.endswith(".outgoing.md"):
                continue
            text = path.read_text(encoding="utf-8")
            identifier = _ARTIFACT_ID.search(text)
            status = _STATUS.search(text)
            if identifier is not None:
                found[identifier.group(1)] = status.group(1) if status else "unknown"
    return found


def _realised() -> set[str]:
    """Requirements something claims to realise — the first link, read from the model's own edges."""
    realised: set[str] = set()
    for root in MODEL_ROOTS:
        for path in root.rglob("*.outgoing.md"):
            realised.update(_REALISES.findall(path.read_text(encoding="utf-8")))
    return realised


def _declared_verified() -> dict[str, set[str]]:
    """Requirement id -> the files declaring they verify it."""
    verified: dict[str, set[str]] = {}
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".vue"}:
                continue
            if path.name == _SELF or "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            for identifier in _VERIFIES.findall(path.read_text(encoding="utf-8", errors="replace")):
                verified.setdefault(identifier, set()).add(path.relative_to(REPO_ROOT).as_posix())
    return verified


def _short(identifier: str) -> str:
    """`REQ@epoch.random` — the form the model accepts and a register stays readable in."""
    parts = identifier.split(".")
    return ".".join(parts[:2]) if len(parts) > 2 else identifier


#: Requirements whose content *is* other requirements, and the requirements that constitute them.
#:
#: Some requirements assert nothing of their own: their prose says, in as many words, "this is a parent
#: requirement grouping X, Y and Z". Such a requirement is verified exactly when X, Y and Z are, and no
#: test can be written for it directly — a test naming the parent would be a test of one of the
#: children wearing a label.
#:
#: **Read from the prose, by hand, once — not derived from the model's edges.** Deriving it was the
#: obvious move and it is wrong: `authoring-tools` *aggregates* one child and *associates* two more, so
#: a rule reading aggregation alone would clear it on a third of its stated grouping, while a rule
#: reading association too would clear anything adjacent to anything. The edges and the prose disagree,
#: and a gate that resolves that disagreement by picking the convenient one is the register lying with
#: extra steps. So this is a judgement, recorded where a reviewer can check it against the prose.
#:
#: It is *mechanically maintained* even though it is hand-authored: every constituent must itself be
#: verified for the parent to count, so a child that loses its verifier fails the parent too, and
#: `test_every_composition_names_requirements_the_model_has` catches a constituent that stops existing.
#: What that buys is a dependency graph instead of six opaque entries — right now every unresolved
#: parent traces back to exactly two roots, `pSvaRl` and `NfAmrl`.
COMPOSED_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    # "grouping three specific discovery mechanisms: semantic full-text search, metadata-based
    # querying, and graph-based relationship discovery" — named, in that order, in its own prose.
    "REQ@1712870400.F4tfa3": (
        "REQ@1712870400.Cc2Dd2",
        "REQ@1712870400.s5B3gB",
        "REQ@1712870400.eBAa26",
    ),
    # "a parent requirement grouping: write-access-only-via-tools ... and GUI exploration and
    # authoring for humans".
    "REQ@1712870400.5PPAX3": ("REQ@1712870400.m117_R", "REQ@1712870400.NfAmrl"),
    # "the frontmatter (one per file type) and the attribute profile (per specialization ...)".
    "REQ@1777369633.UoHGZy": ("REQ@1712870400.pSvaRl", "REQ@1712870400.6ZR3nk"),
    # Prose is one line ("specific aspects of diagrams should be configurable"), so the constituents
    # come from what it aggregates: the per-file-type frontmatter, and datatype diagram authoring.
    "REQ@1777370410.qpOBOQ": ("REQ@1712870400.pSvaRl", "REQ@1781704600.TbcGSB"),
    # Likewise: the four things it aggregates are what "extensible & configurable" means here.
    "REQ@1777369404.aDohcf": (
        "REQ@1777369067.3cJ1Yi",
        "REQ@1777369633.UoHGZy",
        "REQ@1777370410.qpOBOQ",
        "REQ@1781976357.A5WgC8",
    ),
}


def _verified_by_composition(directly_verified: set[str]) -> set[str]:
    """Parents every one of whose constituents is verified, resolved to a fixed point.

    A fixed point rather than one pass, because a parent may be a constituent of another parent —
    `qpOBOQ` is part of `aDohcf`. Iterating until nothing new resolves means the order entries appear
    in above cannot change the answer, which a single pass would let it do.
    """
    resolved = set(directly_verified)
    while True:
        grown = {
            parent
            for parent, parts in COMPOSED_REQUIREMENTS.items()
            if parent not in resolved and parts and all(part in resolved for part in parts)
        }
        if not grown:
            return resolved - directly_verified
        resolved |= grown


def _owed() -> set[str]:
    """Active, realised, and unverified — the obligation this file is about."""
    status = _requirement_status()
    realised = {_short(r) for r in _realised()}
    verified = {_short(v) for v in _declared_verified()}
    verified |= _verified_by_composition(verified)
    return {
        _short(identifier)
        for identifier, state in status.items()
        if state == "active" and _short(identifier) in realised and _short(identifier) not in verified
    }


#: **Empty, as of 2026-08-02.** Every requirement the model marks active, and something claims to
#: realise, now has an artefact declaring that it verifies it. The register began at eight.
#:
#: Two kinds of entry lived here, and the difference decided who resolved them. *A test nobody has
#: written yet* — the ordinary kind; someone finds the assertion and adds the marker. And *a
#: requirement the product only partly implements*, where writing the verifier is blocked on a
#: decision rather than on effort: marking a fragment would clear the entry while leaving the feature
#: half built, so those stayed owed on purpose.
#:
#: **Four of the eight were recorded as the second kind, and three of those were the first.** That is
#: the lesson worth keeping, because "this needs a decision" is a comfortable place for an entry to
#: sit for a release, and nothing about a register makes anyone re-read the claim behind an entry.
#:
#: * ``pSvaRl`` was recorded as possibly-superseded, "and nothing per-file-type for diagrams". There
#:   is: ``frontmatter.diagram.schema.json`` ships as a repository default, exists in this repository,
#:   and ``check_frontmatter_schema(fm, root, "diagram", …)`` is called from both diagram branches of
#:   the verifier, as it is for ``entity`` and ``outgoing``. Documents are the fourth file type through
#:   ``.arch-repo/documents/{abbr}.json``, exactly as the requirement's own Implementation section
#:   says. Owed a test, not a decision — and being a constituent of three grouping parents, that one
#:   test cleared four entries.
#: * ``eFz3z9`` was recorded as grouping by "subdomain" where the requirement says "entity-type". They
#:   are one axis: an entity is filed at ``model/<domain>/<artifact-type>/``, every ontology loader
#:   builds that leaf from the artifact type, and ``derive_domain`` reads the subdomain out of exactly
#:   that segment. A naming difference, verified as such — including the clause that makes it one, that
#:   no declared type is filed deeper than two segments.
#: * ``NfAmrl`` asserted four things at once, and the browser suite covered three of them across
#:   several specs. It needed the fourth *and* the conjunction, which is one spec walking
#:   browse → connection → diagram → create in a single flow rather than four independent ones.
#: * ``HR7AGz`` genuinely needed an amendment, and a smaller one than "is the design superseded".
#:   Writing the verifier found that documents are keyed by ``title`` where entities and diagrams are
#:   keyed by ``name``, so "all three share the same frontmatter schema" was literally false.
#:   Collapsing those would rename a field in every document in every repository to satisfy a phrase,
#:   so the requirement was amended to claim what is true and deliberate — one ID convention, one
#:   verification pass, one frontmatter *base*, and a per-category label — and verified as amended.
#:
#: Grouping requirements are not in this register at all: see ``COMPOSED_REQUIREMENTS`` above, which
#: resolves a parent once every constituent is verified.
#:
#: Requirements that are active, realised, and not yet declared as verified by anything.
#:
#: Shrink-only, like `NEVER_REQUESTED_OPERATIONS` and `SOURCE_FILE_BASELINE_LIMITS`: an entry leaves
#: when something declares it verifies the requirement, and no entry may be added. Now that it is
#: empty, *any* addition is the statement "we built a feature and nothing checks it" — which is the
#: condition this whole exercise exists to make visible rather than discoverable.
UNVERIFIED_REQUIREMENTS: frozenset[str] = frozenset()


def test_the_scan_finds_the_model_and_the_suite_it_means_to_read() -> None:
    # Without this, a glob that stopped matching would report a fully verified product.
    status = _requirement_status()
    assert len(status) >= 60, len(status)
    assert "active" in set(status.values())
    assert len(_realised()) >= 50, len(_realised())


def test_every_declared_requirement_id_exists_in_the_model() -> None:
    """A declaration naming a requirement the model does not have is the Shape B failure again.

    A renamed or deleted requirement leaves the marker behind, and a marker pointing at nothing reads
    as coverage while verifying a feature that no longer exists.
    """
    known = {_short(identifier) for identifier in _requirement_status()}
    stranded = {
        identifier: sorted(where)
        for identifier, where in _declared_verified().items()
        if _short(identifier) not in known
    }
    assert stranded == {}, (
        "these verification declarations name requirements the model does not declare: "
        f"{ {k: v for k, v in sorted(stranded.items())} }"
    )


def test_no_realised_requirement_loses_its_verifier() -> None:
    grown = sorted(_owed() - UNVERIFIED_REQUIREMENTS)
    assert grown == [], (
        "these requirements are active and something realises them, but nothing declares it verifies "
        "them. Add `@pytest.mark.verifies(\"REQ@...\")` to the test that does, or `@verifies REQ@...` "
        f"in a spec or harness — rather than adding to the register, which only shrinks: {grown}"
    )


def test_every_composition_names_requirements_the_model_has() -> None:
    """A composition pointing at a requirement that no longer exists would resolve its parent on a
    constituent nobody can check — the same stranded-reference failure the marker scan guards against.
    """
    known = {_short(identifier) for identifier in _requirement_status()}
    stranded = {
        parent: sorted(set(parts) - known)
        for parent, parts in COMPOSED_REQUIREMENTS.items()
        if set(parts) - known
    }
    assert stranded == {}, f"compositions naming requirements the model does not declare: {stranded}"
    assert not (set(COMPOSED_REQUIREMENTS) - known), sorted(set(COMPOSED_REQUIREMENTS) - known)


def test_no_composition_is_empty_or_names_itself() -> None:
    # An empty tuple would resolve its parent vacuously; a self-reference would resolve it circularly.
    for parent, parts in COMPOSED_REQUIREMENTS.items():
        assert parts, f"{parent} composes nothing, so it would be verified by default"
        assert parent not in parts, f"{parent} names itself as its own constituent"


def test_a_composed_parent_is_owed_while_any_constituent_is() -> None:
    """The property that makes the hand-authored table safe: a parent cannot outrun its children.

    Stated as a check over the real data rather than a synthetic one, so it fails if the fixed-point
    resolution ever starts clearing a parent whose constituent is still owed.
    """
    owed = _owed()
    for parent, parts in COMPOSED_REQUIREMENTS.items():
        still_owed = sorted(part for part in parts if part in owed)
        if still_owed:
            assert parent in owed, (
                f"{parent} is treated as verified while its constituents {still_owed} are not"
            )


def test_the_register_holds_nothing_that_is_now_verified() -> None:
    covered = sorted(UNVERIFIED_REQUIREMENTS - _owed())
    assert covered == [], (
        f"these are verified now (or no longer active/realised) — remove them from the register: {covered}"
    )
