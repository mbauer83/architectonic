/**
 * Visibility logic for the entity-details derived security attributes panel:
 * the panel is ABSENT (not an empty shell) unless the metrics read succeeded,
 * signals are available, and an active signal snapshot exists for this entity as
 * anchor — locked stores, unconfigured deployments, and anchor-less entities
 * all collapse to absence (F3.14 lens-style gating).
 */
import type { SecurityMetricsPayload } from './SecurityPostureDashboard.helpers'

export const panelVisible = (payload: SecurityMetricsPayload | null): boolean => {
  if (payload === null) return false
  if (payload.availability !== 'available') return false
  if (payload.content_state === 'no_active_snapshot') return false
  return Boolean(payload.basis_snapshot_id)
}

/** Read-only display rows — a pure projection so the template stays dumb and
 * the payload can never leak into any editable form state (I-C10). */
export const displayRows = (payload: SecurityMetricsPayload): { label: string; value: string }[] => {
  const directness = Object.entries(payload.open_component_findings ?? {})
    .map(([kind, count]) => `${kind}: ${count}`)
    .join(', ') || 'none'
  const bands = Object.entries(payload.severity_band_counts ?? {})
    .map(([band, count]) => `${band}: ${count}`)
    .join(', ') || 'none'
  return [
    { label: 'distinct open vulnerabilities', value: String(payload.distinct_open_vulnerabilities ?? 0) },
    { label: 'component findings by directness', value: directness },
    { label: 'findings by severity band', value: bands },
    { label: 'max CVSS score', value: payload.max_cvss_score != null ? `${payload.max_cvss_score} (${payload.max_severity_band ?? 'n/a'})` : '—' },
    { label: 'components', value: String(payload.component_count ?? 0) },
    { label: 'basis', value: `${payload.basis_snapshot_id} · ${payload.basis_activated_at}` },
  ]
}
