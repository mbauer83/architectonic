// Pure helpers for the GRC wizard — unit-testable without a DOM.

export interface GrcStep {
  key: string
  label: string
  /** Assurance node_type created in this step ('' for the coverage step). */
  nodeType: string
  /** assurance_guidance topic for the step's coaching panel ('' = no panel). */
  guidanceTopic: string
}

// GRC flow: Risks → Treatment → Controls → Obligations → Coverage.
export const GRC_STEPS: GrcStep[] = [
  { key: 'risks', label: 'Risks', nodeType: 'risk', guidanceTopic: 'grc-risk' },
  { key: 'treatment', label: 'Treatment', nodeType: 'risk', guidanceTopic: 'grc-risk' },
  { key: 'controls', label: 'Controls', nodeType: 'assurance-constraint', guidanceTopic: 'grc-obligations' },
  { key: 'obligations', label: 'Obligations', nodeType: 'obligation', guidanceTopic: 'grc-obligations' },
  { key: 'coverage', label: 'Coverage', nodeType: '', guidanceTopic: '' },
]

// ISO 31000 risk treatment dispositions.
export const TREATMENT_OPTIONS = ['mitigate', 'transfer', 'avoid', 'accept'] as const
export type Treatment = (typeof TREATMENT_OPTIONS)[number]

export const RISK_LEVELS = ['low', 'medium', 'high'] as const
export type RiskLevel = (typeof RISK_LEVELS)[number]

/** Reference type marking a risk as accountable to an architecture role. */
export const ACCOUNTABLE_REF_TYPE = 'accountable-to'

/** §9 anti-subordination safeguard — surfaced on the coverage dashboard. */
export const ANTI_SUBORDINATION_NOTE =
  'Risk prioritises which constraints to treat first but never closes a safety/security '
  + 'constraint: treatment=accept cannot be the sole disposition of a safety hazard '
  + '(§9 anti-subordination safeguard).'

export interface AssuranceNode {
  node_id: string
  node_type: string
  name: string
  attributes_json?: string
}

export interface AssuranceEdge {
  source_id: string
  target_id: string
  conn_type: string
}

/** Stringify a JSON value as a flat scalar (objects/arrays are JSON-encoded). */
function scalarString(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return `${v}`
  return ''
}

/** Parse a node's `attributes_json` string into a flat string map (never throws). */
export function parseAttributes(node: AssuranceNode): Record<string, string> {
  if (!node.attributes_json) return {}
  try {
    const obj = JSON.parse(node.attributes_json) as unknown
    if (obj && typeof obj === 'object') {
      const out: Record<string, string> = {}
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        out[k] = scalarString(v)
      }
      return out
    }
  } catch {
    return {}
  }
  return {}
}

/** The risk's current treatment disposition ('' when unset). */
export function riskTreatment(node: AssuranceNode): string {
  return parseAttributes(node)['treatment'] ?? ''
}

/** A compact "likelihood × impact" label for a risk ('' when neither is set). */
export function riskScore(node: AssuranceNode): string {
  const attrs = parseAttributes(node)
  const likelihood = attrs['likelihood'] ?? ''
  const impact = attrs['impact'] ?? ''
  if (!likelihood && !impact) return ''
  return `${likelihood || '—'} × ${impact || '—'}`
}

/** Source ids already linked to `targetId` via `connType`. */
export function linkedSourceIds(
  edges: AssuranceEdge[],
  targetId: string,
  connType: string,
): Set<string> {
  return new Set(
    edges.filter((e) => e.target_id === targetId && e.conn_type === connType).map((e) => e.source_id),
  )
}

/** Candidate sources of one type not yet linked to `targetId` via `connType`. */
export function unlinkedSources(
  sources: AssuranceNode[],
  edges: AssuranceEdge[],
  targetId: string,
  connType: string,
): AssuranceNode[] {
  const linked = linkedSourceIds(edges, targetId, connType)
  return sources.filter((s) => !linked.has(s.node_id))
}

export interface GrcGap {
  node_id: string
  name: string
}

export interface GrcCheck {
  passed: boolean
  gap_count: number
  gaps?: GrcGap[]
}

export interface GrcCompleteResponse {
  passed: boolean
  checks: Record<string, GrcCheck>
}

export interface GrcCompleteSummary {
  passed: boolean
  failed: { key: string; gapCount: number }[]
}

export function summariseGrcComplete(resp: GrcCompleteResponse): GrcCompleteSummary {
  const failed = Object.entries(resp.checks)
    .filter(([, c]) => !c.passed)
    .map(([key, c]) => ({ key, gapCount: c.gap_count }))
  return { passed: resp.passed, failed }
}

/**
 * Node ids flagged as gaps by a named completeness check (e.g. `risk_has_owner`).
 * The wizard uses this as the single source of truth for per-risk treatment/owner
 * status, so the owner rule (accountable-to edge OR arch-ref) stays server-side.
 */
export function gapNodeIds(resp: GrcCompleteResponse | null, checkKey: string): Set<string> {
  const gaps = resp?.checks?.[checkKey]?.gaps ?? []
  return new Set(gaps.map((g) => g.node_id))
}

/** Which step keys already have meaningful content (for the stepper badges). */
export function grcStepBadges(nodes: AssuranceNode[]): Set<string> {
  const keys = new Set<string>()
  const risks = nodes.filter((n) => n.node_type === 'risk')
  if (risks.length) keys.add('risks')
  if (risks.some((r) => riskTreatment(r))) keys.add('treatment')
  if (nodes.some((n) => n.node_type === 'assurance-constraint')) keys.add('controls')
  if (nodes.some((n) => n.node_type === 'obligation')) keys.add('obligations')
  return keys
}
