"""Verifier rules for view_derivations frontmatter.

E409: binding derived_from references unknown view_derivations.id.
E410: duplicate view_derivations.id within a diagram.
E411: unknown or unregistered strategy + version combination.
E412: unsupported pre_filter key for the declared strategy version.
E413: invalid repo_scope value in source_model_snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.viewpoints.view_derivations import VALID_REPO_SCOPES

if TYPE_CHECKING:
    from src.application.derivation.strategy_registry import DerivationStrategyCatalog


def collect_view_derivation_ids(fm: dict) -> set[str]:
    """Return the set of declared view_derivations ids for derived_from validation."""
    raw_vds = fm.get("view_derivations")
    if not raw_vds or not isinstance(raw_vds, list):
        return set()
    return {str(raw["id"]) for raw in raw_vds if isinstance(raw, dict) and raw.get("id") is not None}


def check_view_derivations(
    fm: dict,
    result: VerificationResult,
    loc: str,
    catalog: "DerivationStrategyCatalog | None" = None,
) -> None:
    """Validate the view_derivations block in diagram frontmatter.

    Silently returns when view_derivations is absent or empty.
    E411/E412 strategy checks are skipped when catalog is None.
    """
    raw_vds = fm.get("view_derivations")
    if not raw_vds or not isinstance(raw_vds, list):
        return

    seen_ids: set[str] = set()
    for raw in raw_vds:
        if not isinstance(raw, dict):
            continue

        vd_id = str(raw.get("id") or "(no-id)")

        # E410: duplicate id
        if vd_id in seen_ids:
            result.issues.append(Issue(
                Severity.ERROR, "E410",
                f"view_derivations: duplicate id '{vd_id}'",
                loc,
            ))
        else:
            seen_ids.add(vd_id)

        # E413: invalid repo_scope
        snapshot = raw.get("source_model_snapshot")
        if isinstance(snapshot, dict):
            repo_scope = str(snapshot.get("repo_scope", ""))
            if repo_scope not in VALID_REPO_SCOPES:
                result.issues.append(Issue(
                    Severity.ERROR, "E413",
                    (
                        f"view_derivations '{vd_id}': invalid repo_scope '{repo_scope}'; "
                        f"expected one of: {sorted(VALID_REPO_SCOPES)}"
                    ),
                    loc,
                ))

        # E411 + E412: strategy registration and supported filters
        strategy = str(raw.get("strategy") or "")
        sv = raw.get("strategy_version")
        version = int(sv) if isinstance(sv, (int, float)) else 0
        _check_strategy(vd_id, strategy, version, raw, result, loc, catalog=catalog)


def check_all_view_derivations(
    fm: dict,
    result: VerificationResult,
    loc: str,
    catalog: "DerivationStrategyCatalog | None" = None,
) -> None:
    """Run all view_derivations verifier rules for a diagram frontmatter dict.

    Combines structural validation (E410, E411, E412, E413) with binding
    derived_from cross-reference validation (E409).  Call once per diagram.
    E411/E412 strategy checks are skipped when catalog is None.
    """
    vd_ids = collect_view_derivation_ids(fm)
    check_view_derivations(fm, result, loc, catalog=catalog)
    check_bindings_derived_from(fm, vd_ids, result, loc)


def check_bindings_derived_from(
    fm: dict,
    view_derivation_ids: set[str],
    result: VerificationResult,
    loc: str,
) -> None:
    """E409: validate that each binding's derived_from references a known view_derivations id."""
    raw_bindings = fm.get("bindings")
    if not raw_bindings or not isinstance(raw_bindings, list):
        return

    for raw in raw_bindings:
        if not isinstance(raw, dict):
            continue
        derived_from = raw.get("derived_from")
        if derived_from is None:
            continue
        derived_from_str = str(derived_from)
        if derived_from_str not in view_derivation_ids:
            binding_id = str(raw.get("id") or "(no-id)")
            result.issues.append(Issue(
                Severity.ERROR, "E409",
                (
                    f"binding '{binding_id}': derived_from '{derived_from_str}' "
                    "does not reference a known view_derivations.id"
                ),
                loc,
            ))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _check_strategy(
    vd_id: str,
    strategy: str,
    version: int,
    raw: dict[str, object],
    result: VerificationResult,
    loc: str,
    catalog: "DerivationStrategyCatalog | None" = None,
) -> None:
    if not strategy or catalog is None:
        return

    spec = catalog.lookup_strategy(strategy, version)
    if spec is None:
        result.issues.append(Issue(
            Severity.ERROR, "E411",
            f"view_derivations '{vd_id}': unknown strategy '{strategy}' version {version}",
            loc,
        ))
        return  # cannot check filters without a known spec

    params = raw.get("parameters")
    if not isinstance(params, dict):
        return
    pre_filters = params.get("pre_filters")
    if not isinstance(pre_filters, dict):
        return

    for key in pre_filters:
        if key not in spec.supported_filters:
            result.issues.append(Issue(
                Severity.ERROR, "E412",
                (
                    f"view_derivations '{vd_id}': pre_filter key '{key}' is not "
                    f"supported by strategy '{strategy}' v{version} "
                    f"(supported: {sorted(spec.supported_filters)})"
                ),
                loc,
            ))
