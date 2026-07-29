/**
 * C-S4 panel gating (F3.14) + read-only projection (I-C10): the panel is
 * ABSENT for locked/unavailable/anchor-less states, and its display rows are
 * a pure projection — nothing bindable to any edit form.
 */
import { describe, it, expect } from 'vitest'
import { displayRows, panelVisible } from '../DerivedSecurityAttributesPanel.helpers'
import type { SecurityMetricsPayload } from '../SecurityPostureDashboard.helpers'

const withRun: SecurityMetricsPayload = {
  availability: 'available',
  content_state: 'complete',
  basis_snapshot_id: 'SNAP@1',
  basis_activated_at: '2026-07-20T00:00:00Z',
  computed_classification: 'TLP:AMBER',
  distinct_open_vulnerabilities: 3,
  finding_total: 4,
  component_count: 107,
  open_component_findings: { direct: 1, transitive: 3 },
  severity_band_counts: { high: 2, medium: 2 },
  max_cvss_score: 8.1,
  max_severity_band: 'high',
}

describe('panelVisible', () => {
  it('shows only with an available payload anchored to an active run', () => {
    expect(panelVisible(withRun)).toBe(true)
  })

  it('is absent for every gated state', () => {
    expect(panelVisible(null)).toBe(false)  // fetch failed / locked (423)
    expect(panelVisible({ availability: 'unavailable', reason: 'x' })).toBe(false)
    expect(panelVisible({ ...withRun, content_state: 'no_active_snapshot', basis_snapshot_id: null })).toBe(false)
    expect(panelVisible({ ...withRun, basis_snapshot_id: null })).toBe(false)
  })
})

describe('displayRows', () => {
  it('projects the read-only vocabulary with directness and band figures', () => {
    const rows = Object.fromEntries(displayRows(withRun).map((r) => [r.label, r.value]))
    expect(rows['distinct open vulnerabilities']).toBe('3')
    expect(rows['component findings by directness']).toBe('direct: 1, transitive: 3')
    expect(rows['findings by severity band']).toBe('high: 2, medium: 2')
    expect(rows['max CVSS score']).toBe('8.1 (high)')
    expect(rows.basis).toContain('SNAP@1')
  })

  it('renders honest placeholders when nothing scored', () => {
    const rows = Object.fromEntries(displayRows({
      ...withRun, max_cvss_score: null, open_component_findings: {}, severity_band_counts: {},
    }).map((r) => [r.label, r.value]))
    expect(rows['max CVSS score']).toBe('—')
    expect(rows['component findings by directness']).toBe('none')
  })
})
