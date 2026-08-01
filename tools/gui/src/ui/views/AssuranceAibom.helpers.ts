// Pure helpers for the AI-BOM panel — unit-testable without a DOM.
//
// The ML-BOM is DERIVED from the architecture model (entities carrying an AI specialization),
// so the panel no longer assembles a component list or assigns per-component roles — it scans
// (assistive), exports the model-derived BOM, and shows coverage. The old role/selection
// helpers are gone with that flow.

import {
  decodeAiBomCoverage,
  decodeAiBomScan,
  type AiBomCandidate,
  type AiBomComponentCoverage,
  type AiBomCoverage,
} from '../../domain/schemas/assurance-aibom'

/* The routes' own shapes, decoded. These were two interfaces and two field-by-field coercions —
   `asStr`, `asNum`, `asStrList` — which is what a client writes when the server publishes no contract.
   They agreed with the routes only by having been written carefully, and a coercion that yields `''`
   for a missing name reads exactly like a component that has none. */
export type ScanCandidate = AiBomCandidate

export const parseCandidates = (body: unknown): ScanCandidate[] => [...decodeAiBomScan(body)]

/** Confidence band for a candidate score (drives the badge colour). */
export function scoreBand(score: number): 'high' | 'medium' | 'low' {
  return score >= 50 ? 'high' : score >= 30 ? 'medium' : 'low'
}

// ── Coverage ──────────────────────────────────────────────────────────────────

export type ComponentCoverage = AiBomComponentCoverage
export type AibomCoverage = AiBomCoverage

export const parseCoverage = (body: unknown): AibomCoverage => decodeAiBomCoverage(body)

export function componentHasBlockingGap(c: ComponentCoverage): boolean {
  return (
    c.missing_required_attributes.length > 0 ||
    c.missing_dataset_linkage ||
    c.missing_governance
  )
}
