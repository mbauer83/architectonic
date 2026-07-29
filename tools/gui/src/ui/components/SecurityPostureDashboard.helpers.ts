/**
 * Pure logic for the security-posture dashboard: metric payload typing, the
 * closed availability/content states as user-facing messages, and VEX form
 * validation mirroring the server rules (suppressing statuses require a
 * justification) so obvious mistakes fail before the request.
 */

export interface SecurityMetricsPayload {
  availability: 'available' | 'unavailable'
  content_state?: 'complete' | 'visibility_limited' | 'no_active_snapshot' | 'no_findings'
  reason?: string
  visibility_limited?: boolean
  basis_snapshot_id?: string | null
  basis_activated_at?: string | null
  computed_classification?: string | null
  component_count?: number
  finding_total?: number
  open_component_findings?: Record<string, number>
  distinct_open_vulnerabilities?: number
  severity_band_counts?: Record<string, number>
  max_cvss_score?: number | null
  max_severity_band?: string | null
  applicability_unknown_count?: number
  unknown_severity_finding_count?: number
  suppressed_finding_count?: number
}

export const stateMessage = (payload: SecurityMetricsPayload): string | null => {
  if (payload.availability === 'unavailable') {
    return payload.reason ?? 'signals unavailable — retry'
  }
  switch (payload.content_state) {
    case 'no_active_snapshot':
      return 'No security signal snapshot has been activated for this anchor yet'
        + ' — run the ingest script to produce one.'
    case 'no_findings':
      return null // the zeroes are real
    case 'visibility_limited':
      return 'Some contributing records are above your classification ceiling — every figure below covers visible records only.'
    default:
      return null
  }
}

export const showsMetrics = (payload: SecurityMetricsPayload): boolean =>
  payload.availability === 'available' && payload.content_state !== 'no_active_snapshot'

const SUPPRESSING = new Set(['not_affected', 'fixed'])
export const VEX_STATUSES = ['affected', 'not_affected', 'fixed', 'under_investigation'] as const

export interface VexFormValues {
  canonical_component_id: string
  canonical_vulnerability_id: string
  vex_status: string
  justification: string
  author: string
}

export const vexFormErrors = (values: VexFormValues): string[] => {
  const errors: string[] = []
  if (!values.canonical_component_id.trim()) errors.push('component (purl with version) is required')
  if (!values.canonical_vulnerability_id.trim()) errors.push('canonical vulnerability id is required')
  if (!values.author.trim()) errors.push('author is required')
  if (SUPPRESSING.has(values.vex_status) && !values.justification.trim()) {
    errors.push(`vex_status '${values.vex_status}' suppresses a finding and requires a justification`)
  }
  return errors
}
