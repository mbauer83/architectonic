// Pure helpers for the supply-chain wizard — unit-testable without a DOM.

export interface SupplyStep {
  key: string
  label: string
  /** Whether this step requires an ArchiMate scope anchor to be selected first. */
  needsAnchor: boolean
}

// Supply-chain flow: Scope (ArchiMate anchor) → Ingest SBOM → Components →
// Vulnerabilities → Posture & VEX → AI-BOM. The AI-BOM step is
// store-/architecture-wide (candidate scan, ML-BOM export), so it does not require
// a per-scope anchor.
//
// The ingest step delegates to the SAME component the entity page uses, which posts
// to the same gated, audited, idempotent command as the CLI, MCP and REST surfaces.
// The browser is another adapter, not a bypass.
export const SUPPLY_STEPS: SupplyStep[] = [
  { key: 'scope', label: 'Scope', needsAnchor: false },
  { key: 'ingest', label: 'Ingest SBOM', needsAnchor: true },
  { key: 'components', label: 'Components', needsAnchor: true },
  { key: 'vulnerabilities', label: 'Vulnerabilities', needsAnchor: true },
  { key: 'posture', label: 'Posture & VEX', needsAnchor: true },
  { key: 'aibom', label: 'AI-BOM', needsAnchor: false },
]

/**
 * Admissible ArchiMate anchor types, for the scope picker's synchronous filter.
 *
 * The BACKEND owns this vocabulary (`/api/assurance/signal-anchor-types`) and
 * enforces it on ingest; the panel fetches it. This copy exists only because the
 * picker needs the list before any request completes, and a test asserts the two
 * stay identical so the duplication cannot drift silently.
 *
 * Coarse by design: the backend additionally restricts by SPECIALIZATION (an
 * application-component may anchor an SBOM when it is a service or unspecialized,
 * but not as a module or endpoint), which the picker cannot express. The ingest
 * itself refuses the narrower cases.
 */
export const ADMISSIBLE_ANCHOR_TYPES = [
  'application-component',
  'node',
  'system-software',
] as const

export const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'unknown'] as const

export interface VulnRecord {
  vuln_id?: string
  id?: string
  severity?: string
  purl?: string
  summary?: string
}

/** Count vulnerabilities by severity in canonical order (zero-count buckets dropped). */
export function summariseSeverities(vulns: VulnRecord[]): { severity: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const v of vulns) {
    const sev = (v.severity ?? 'unknown').toLowerCase()
    counts.set(sev, (counts.get(sev) ?? 0) + 1)
  }
  const ordered: { severity: string; count: number }[] = []
  for (const sev of SEVERITY_ORDER) {
    const c = counts.get(sev)
    if (c) { ordered.push({ severity: sev, count: c }); counts.delete(sev) }
  }
  // Any non-canonical severities, appended as-is.
  for (const [severity, count] of counts) ordered.push({ severity, count })
  return ordered
}

/** A component row of the active signal snapshot. */
export interface BomComponent {
  component_id?: string
  name?: string
  version?: string
  component_type?: string
  purl?: string
  directness?: string
}
