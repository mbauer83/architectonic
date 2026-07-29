/**
 * Posture dashboard logic: closed availability/content states as honest
 * user messages (no_active_snapshot never renders zeros as "all clear"), and VEX
 * form validation mirroring the server's justification rule.
 */
import { describe, it, expect } from 'vitest'
import {
  stateMessage, showsMetrics, vexFormErrors,
  type SecurityMetricsPayload, type VexFormValues,
} from '../SecurityPostureDashboard.helpers'

const base: SecurityMetricsPayload = { availability: 'available', content_state: 'complete' }

describe('state handling', () => {
  it('unavailable shows the reason and no metrics', () => {
    const payload: SecurityMetricsPayload = { availability: 'unavailable', reason: 'retry' }
    expect(stateMessage(payload)).toBe('retry')
    expect(showsMetrics(payload)).toBe(false)
  })

  it('no_active_snapshot explains itself and hides the grid — never fake zeros', () => {
    const payload: SecurityMetricsPayload = { ...base, content_state: 'no_active_snapshot' }
    expect(stateMessage(payload)).toContain('ingest')
    expect(showsMetrics(payload)).toBe(false)
  })

  it('visibility_limited shows metrics WITH the coverage caveat', () => {
    const payload: SecurityMetricsPayload = { ...base, content_state: 'visibility_limited' }
    expect(stateMessage(payload)).toContain('ceiling')
    expect(showsMetrics(payload)).toBe(true)
  })

  it('complete and no_findings render silently', () => {
    expect(stateMessage(base)).toBeNull()
    expect(stateMessage({ ...base, content_state: 'no_findings' })).toBeNull()
    expect(showsMetrics(base)).toBe(true)
  })
})

describe('vex form validation', () => {
  const valid: VexFormValues = {
    canonical_component_id: 'pkg:pypi/requests@2.31.0',
    canonical_vulnerability_id: 'VID@abc',
    vex_status: 'not_affected',
    justification: 'code path unused',
    author: 'analyst',
  }

  it('accepts a complete suppressing assessment', () => {
    expect(vexFormErrors(valid)).toEqual([])
  })

  it('requires justification only for suppressing statuses', () => {
    expect(vexFormErrors({ ...valid, justification: '' })).toHaveLength(1)
    expect(vexFormErrors({ ...valid, vex_status: 'fixed', justification: '' })).toHaveLength(1)
    expect(vexFormErrors({ ...valid, vex_status: 'affected', justification: '' })).toEqual([])
    expect(vexFormErrors({ ...valid, vex_status: 'under_investigation', justification: '' })).toEqual([])
  })

  it('requires the key fields and author', () => {
    const errors = vexFormErrors({
      canonical_component_id: '', canonical_vulnerability_id: '',
      vex_status: 'affected', justification: '', author: '',
    })
    expect(errors).toHaveLength(3)
  })
})
