/**
 * Pure logic for the component-vulnerability view: payload typing, grouping
 * findings under the component they affect, severity ordering, and the label a
 * finding is known by.
 *
 * A finding carries both a canonical vulnerability id (VID@…, the identity that
 * merges CVE/GHSA/PYSEC) and the feed id its scanner reported, inside
 * `provenance`. The feed id is what an analyst recognises, so it is what we
 * SHOW; the canonical id is what we LINK with, because it resolves regardless of
 * which feed named it.
 */

export interface SecurityFinding {
  finding_id: string
  canonical_vulnerability_id: string
  severity_band?: string | null
  cvss_score?: number | null
  cvss_vector?: string | null
  applicability?: string | null
  provenance?: string | null
  component_name?: string | null
  component_purl?: string | null
  component_directness?: string | null
}

export interface FindingsPayload {
  findings?: SecurityFinding[]
  count?: number
  withheld?: number
  reason?: string
}

export interface ComponentGroup {
  componentName: string
  componentPurl: string
  directness: string
  findings: SecurityFinding[]
  maxSeverityBand: string | null
}

/** Ascending severity. Anything unrecognised sorts below `none`. */
export const SEVERITY_ORDER = ['none', 'low', 'medium', 'high', 'critical'] as const

export const severityRank = (band?: string | null): number => {
  const index = SEVERITY_ORDER.indexOf((band ?? '') as (typeof SEVERITY_ORDER)[number])
  return index === -1 ? -1 : index
}

export const parseProvenance = (finding: SecurityFinding): Record<string, string> => {
  if (!finding.provenance) return {}
  try {
    const parsed: unknown = JSON.parse(finding.provenance)
    if (parsed === null || typeof parsed !== 'object') return {}
    return parsed as Record<string, string>
  } catch {
    // Provenance is opaque metadata; malformed JSON must not break the view.
    return {}
  }
}

/** What the analyst recognises: the feed id when known, else the canonical id. */
export const vulnerabilityLabel = (finding: SecurityFinding): string =>
  parseProvenance(finding).osv_id ?? finding.canonical_vulnerability_id

/** What we navigate by: always the canonical id, which resolves via any alias. */
export const vulnerabilityKey = (finding: SecurityFinding): string =>
  finding.canonical_vulnerability_id

const maxBand = (findings: SecurityFinding[]): string | null => {
  let best: string | null = null
  for (const finding of findings) {
    if (severityRank(finding.severity_band) > severityRank(best)) {
      best = finding.severity_band ?? null
    }
  }
  return best
}

/**
 * Group findings by the component they affect, worst component first, so the
 * thing needing attention is at the top rather than wherever the id sort put it.
 */
export const groupByComponent = (findings: SecurityFinding[]): ComponentGroup[] => {
  const groups = new Map<string, ComponentGroup>()
  for (const finding of findings) {
    const key = finding.component_purl || finding.component_name || 'unknown'
    let group = groups.get(key)
    if (!group) {
      group = {
        componentName: finding.component_name ?? 'unknown',
        componentPurl: finding.component_purl ?? '',
        directness: finding.component_directness ?? 'unknown',
        findings: [],
        maxSeverityBand: null,
      }
      groups.set(key, group)
    }
    group.findings.push(finding)
  }
  for (const group of groups.values()) {
    group.findings.sort((a, b) => severityRank(b.severity_band) - severityRank(a.severity_band))
    group.maxSeverityBand = maxBand(group.findings)
  }
  return [...groups.values()].sort((a, b) => {
    const bySeverity = severityRank(b.maxSeverityBand) - severityRank(a.maxSeverityBand)
    return bySeverity !== 0 ? bySeverity : a.componentName.localeCompare(b.componentName)
  })
}

/**
 * Withheld records are surfaced, never silently dropped: a filtered list that
 * looks complete is the failure mode exposure filtering must not produce.
 */
export const withheldNote = (payload: FindingsPayload): string | null => {
  const withheld = payload.withheld ?? 0
  if (withheld <= 0) return null
  return `${withheld} record${withheld === 1 ? '' : 's'} above your classification ceiling `
    + 'are not shown.'
}

export const emptyMessage = (payload: FindingsPayload): string | null => {
  if (payload.reason) return payload.reason
  if ((payload.findings ?? []).length > 0) return null
  if ((payload.withheld ?? 0) > 0) {
    // Distinct from "clean": everything there is, is hidden from this caller.
    return 'No findings are visible at your classification ceiling.'
  }
  return 'No vulnerability findings in the active snapshot for this entity.'
}
