// Pure helpers for the AI-BOM panel — unit-testable without a DOM.
//
// The ML-BOM is DERIVED from the architecture model (entities carrying an AI specialization),
// so the panel no longer assembles a component list or assigns per-component roles — it scans
// (assistive), exports the model-derived BOM, and shows coverage. The old role/selection
// helpers are gone with that flow.

/** Coerce an unknown to a string, but only for primitives (objects → ''). */
function asStr(v: unknown): string {
  return typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : ''
}

function asNum(v: unknown): number {
  return typeof v === 'number' ? v : 0
}

function asStrList(v: unknown): string[] {
  return Array.isArray(v) ? v.map(asStr).filter((s) => s !== '') : []
}

export interface ScanCandidate {
  entity_id: string
  name: string
  entity_type: string
  score: number
  reasons: string[]
}

export function parseCandidates(body: unknown): ScanCandidate[] {
  if (!body || typeof body !== 'object') return []
  const raw = (body as Record<string, unknown>)['candidates']
  if (!Array.isArray(raw)) return []
  return raw
    .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
    .map((c) => ({
      entity_id: asStr(c['entity_id']),
      name: asStr(c['name']),
      entity_type: asStr(c['entity_type']),
      score: asNum(c['score']),
      reasons: asStrList(c['reasons']),
    }))
}

/** Confidence band for a candidate score (drives the badge colour). */
export function scoreBand(score: number): 'high' | 'medium' | 'low' {
  return score >= 50 ? 'high' : score >= 30 ? 'medium' : 'low'
}

// ── Coverage ──────────────────────────────────────────────────────────────────

export interface ComponentCoverage {
  entity_id: string
  name: string
  specialization: string
  missing_required_attributes: string[]
  missing_recommended_attributes: string[]
  missing_dataset_linkage: boolean
  missing_governance: boolean
}

export interface AibomCoverage {
  components: ComponentCoverage[]
  unbound_roles: string[]
}

export function parseCoverage(body: unknown): AibomCoverage {
  const obj = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>
  const rawComponents = Array.isArray(obj['components']) ? obj['components'] : []
  const components = rawComponents
    .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
    .map((c) => ({
      entity_id: asStr(c['entity_id']),
      name: asStr(c['name']),
      specialization: asStr(c['specialization']),
      missing_required_attributes: asStrList(c['missing_required_attributes']),
      missing_recommended_attributes: asStrList(c['missing_recommended_attributes']),
      missing_dataset_linkage: c['missing_dataset_linkage'] === true,
      missing_governance: c['missing_governance'] === true,
    }))
  return { components, unbound_roles: asStrList(obj['unbound_roles']) }
}

/** A component is BLOCKING-clean when it has no required-attribute / dataset / governance gap;
 * missing recommended attributes are advisory and do not count against it. */
export function componentHasBlockingGap(c: ComponentCoverage): boolean {
  return (
    c.missing_required_attributes.length > 0 ||
    c.missing_dataset_linkage ||
    c.missing_governance
  )
}
