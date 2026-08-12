"""Rule: a diagram body declares each alias once, because PlantUML does not say when it does not.

A second ``as ALIAS`` for an alias already declared is not an error in PlantUML — it is read as a
*reference* to the element already created. So a body that declares one element inside two
containers renders the second container **empty**, and the containment it was drawing disappears
from the picture. Nothing downstream objects: the body parses, `entity-ids-used` and
`connection-ids-used` both resolve, and `artifact_verify` answered ``valid: true``. That is the hole
this rule closes — the reported view carried 29 declarations for 19 aliases with four empty boxes,
and the only signal available to its author was the picture looking wrong.

The generator can no longer produce one (see ``_NestingForest``), which is why this is stated over
the *body* rather than over the generator: a hand-authored body, a body edited through the write
path, and a body from a future renderer all reach the same reader.

**Scope: bodies written in the element-declaration vocabulary.** A diagram type that owns its own
entity types (``diagram_only_types`` — datatype, C4, sequence, …) speaks its own body language, and
its bodies carry unquoted prose that no reading of `as ALIAS` can tell from code: the repository's
own persistence-model datatype diagram describes a record "persisted **as a** single markdown file"
twice, which is a duplicate declaration of `a` to any reader of the syntax and an element to none.
Measured across the 48 bodies in this repository, that description is the only hit; every ArchiMate
diagram declares each alias exactly once.

**The `as` form only, counted raw.** Two readings of the owner's are deliberately not used here.
``macro_alias_declared_on`` answers the first argument of any ``Name(ALIAS, …)`` call, which on an
ArchiMate body is a *relation* — ``Rel_Realization(REQ_kOU3al, OUT_620dTh, "")`` names two aliases
and declares neither, and reading it as a declaration reported three duplicates in a clean diagram
in this repository. And ``normalize_puml_alias`` folds `-` to `_`, which PlantUML does not: two
aliases differing only there are two elements, and folding them would invent a duplicate. What is
counted is what PlantUML itself would treat as the same declaration.

**Error, not warning.** The defect is silent by construction — a warning would be read as a style
note about a body that has already lost a relationship, and severity is what decides whether a
refresh may write it. Nothing in either repository has to change to satisfy it.
"""

from __future__ import annotations

from collections import Counter

from src.application.puml_alias_declarations import declared_aliases
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.modules.catalogs import DiagramTypeCatalog


def _body_declares_elements(fm: dict, diagram_type_catalog: DiagramTypeCatalog) -> bool:
    """True when the body is a set of element declarations rather than a type's own vocabulary."""
    module = diagram_type_catalog.find_diagram_type(str(fm.get("diagram-type", "archimate")))
    return module is None or not module.ui_config.diagram_only_types


def check_puml_alias_declarations(
    content: str,
    fm: dict,
    result: VerificationResult,
    loc: str,
    *,
    diagram_type_catalog: DiagramTypeCatalog,
) -> None:
    """E318: no alias is declared twice — a second declaration silently empties a container."""
    if not _body_declares_elements(fm, diagram_type_catalog):
        return

    counts = Counter(declaration.alias for declaration in declared_aliases(content))
    for alias, times in sorted(counts.items()):
        if times > 1:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E318",
                    f"diagram body declares alias '{alias}' {times} times; PlantUML treats every "
                    "declaration after the first as a reference, so that container renders empty "
                    "and the containment it draws is lost from the picture",
                    loc,
                )
            )
