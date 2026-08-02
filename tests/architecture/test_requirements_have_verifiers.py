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


def _owed() -> set[str]:
    """Active, realised, and unverified — the obligation this file is about."""
    status = _requirement_status()
    realised = {_short(r) for r in _realised()}
    verified = {_short(v) for v in _declared_verified()}
    return {
        _short(identifier)
        for identifier, state in status.items()
        if state == "active" and _short(identifier) in realised and _short(identifier) not in verified
    }


#: Requirements that are active, realised, and not yet declared as verified by anything.
#:
#: Shrink-only, like `NEVER_REQUESTED_OPERATIONS` and `SOURCE_FILE_BASELINE_LIMITS`: an entry leaves
#: when something declares it verifies the requirement, and no entry may be added. A *new* entry is
#: the statement "we built a feature and nothing checks it", which is the condition this whole
#: exercise exists to make visible rather than discoverable.
UNVERIFIED_REQUIREMENTS: frozenset[str] = frozenset(
    {
        "REQ@1712870400.5PPAX3",
        "REQ@1712870400.6ZR3nk",
        "REQ@1712870400.Aa1Bb1",
        "REQ@1712870400.Cc2Dd2",
        "REQ@1712870400.Ee3Ff3",
        "REQ@1712870400.F4tfa3",
        "REQ@1712870400.Gg4Hh4",
        "REQ@1712870400.HR7AGz",
        "REQ@1712870400.Ii5Jj5",
        "REQ@1712870400.JTRw1x",
        "REQ@1712870400.KeGCZE",
        "REQ@1712870400.Kk6Ll6",
        "REQ@1712870400.NfAmrl",
        "REQ@1712870400.O-Ppmp",
        "REQ@1712870400.V5EdQk",
        "REQ@1712870400.cz8L4W",
        "REQ@1712870400.eBAa26",
        "REQ@1712870400.kOU3al",
        "REQ@1712870400.m117_R",
        "REQ@1712870400.pSvaRl",
        "REQ@1712870400.peinbQ",
        "REQ@1712870400.s5B3gB",
        "REQ@1712870400.vlMSrd",
        "REQ@1776637159.X5jYC0",
        "REQ@1777369067.3cJ1Yi",
        "REQ@1777369240.dGaLkH",
        "REQ@1777369404.aDohcf",
        "REQ@1777369633.UoHGZy",
        "REQ@1777370410.qpOBOQ",
        "REQ@1777371781.v0TJX4",
        "REQ@1777371979.W-G4L5",
        "REQ@1777372175.eFz3z9",
        "REQ@1777372455.LnytwA",
        "REQ@1777372662.64JvM1",
        "REQ@1780505955.MdtfC3",
        "REQ@1780655839.IOPvsf",
        "REQ@1780655839.IriicS",
        "REQ@1780655839.JpAJkO",
        "REQ@1780655839.az20QC",
        "REQ@1780655839.kjBJrh",
        "REQ@1780655839.urjIeU",
        "REQ@1780655839.ySK1bT",
        "REQ@1781704600.TbcGSB",
        "REQ@1781886720.VJ2ml-",
        "REQ@1781886727.m0KjkK",
        "REQ@1781976356.EPkivp",
        "REQ@1781976357.A5WgC8",
        "REQ@1782080517.IIl8-4",
        "REQ@1783870978.mUf9JQ",
        "REQ@1783870981.mdH8Uv",
        "REQ@1783870983.rWP8Hl",
        "REQ@1783872530.VyosDa",
        "REQ@1784502378.Z09NNS",
        "REQ@1784502380.oiS35Q",
        "REQ@1784609467.2I2fS1",
        "REQ@1784609467.na0At3",
        "REQ@1785058330.-LmyST",
    }
)


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


def test_the_register_holds_nothing_that_is_now_verified() -> None:
    covered = sorted(UNVERIFIED_REQUIREMENTS - _owed())
    assert covered == [], (
        f"these are verified now (or no longer active/realised) — remove them from the register: {covered}"
    )
