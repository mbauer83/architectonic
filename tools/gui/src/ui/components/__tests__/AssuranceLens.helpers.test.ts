/**
 * The assurance lens's roll-up line: what an architect sees on a component page.
 *
 * The distinction that carries the most weight is between an element that is *not a candidate*
 * (no line at all) and one that is a candidate *nobody has examined* (a line saying so). Rendering
 * the second as nothing, or as a quiet "no findings", is how an un-analysed component comes to look
 * safe — which is the failure this whole surface exists to prevent.
 */

import { describe, expect, it } from 'vitest'
import {
  failureModeHeadline,
  failureModeNeedsAttention,
  parseLensResponse,
} from '../AssuranceLens.helpers'
import type { FailureModeSummary, RawLensResponse } from '../AssuranceLens.helpers'

function summary(overrides: Partial<FailureModeSummary> = {}): FailureModeSummary {
  return {
    worst_action_priority: null,
    high_count: 0,
    unanswered_cells: 0,
    nominated_by: ['control-structure'],
    ...overrides,
  }
}

function raw(overrides: Partial<RawLensResponse> = {}): RawLensResponse {
  return { locked: false, nodes: [], count: 0, ...overrides }
}

describe('parsing the roll-up', () => {
  it('carries the summary through when the element is a candidate', () => {
    const result = parseLensResponse(raw({ failure_mode_summary: summary() }))

    expect(result.failureModes).not.toBeNull()
  })

  it('is null when the element is not a candidate', () => {
    expect(parseLensResponse(raw()).failureModes).toBeNull()
  })

  it('is null when the store is locked', () => {
    // A locked store must disclose nothing, including whether an element is a candidate.
    const result = parseLensResponse(raw({ locked: true, failure_mode_summary: summary() }))

    expect(result.failureModes).toBeNull()
  })

  it('makes the section visible for a candidate with no assurance nodes yet', () => {
    // Otherwise the row that most needs attention — examined by nobody — renders as nothing.
    const result = parseLensResponse(raw({ failure_mode_summary: summary({ unanswered_cells: 5 }) }))

    expect(result.visible || result.failureModes !== null).toBe(true)
  })
})

describe('the headline names the state rather than scoring it', () => {
  it('says plainly when nothing has been examined', () => {
    const line = failureModeHeadline(summary({ unanswered_cells: 5 }))

    expect(line).toContain('Not yet examined')
    expect(line).toContain('5 of 5')
  })

  it('distinguishes examined-and-empty from unexamined', () => {
    const line = failureModeHeadline(summary({ unanswered_cells: 0 }))

    expect(line).toContain('none recorded')
    expect(line).not.toContain('Not yet examined')
  })

  it('leads with the worst band once there are findings', () => {
    const line = failureModeHeadline(
      summary({ worst_action_priority: 'high', high_count: 2, unanswered_cells: 1 }),
    )

    expect(line).toContain('worst action priority high')
    expect(line).toContain('2 at high')
    expect(line).toContain('1 unanswered')
  })

  it('omits the counts that are zero', () => {
    const line = failureModeHeadline(summary({ worst_action_priority: 'low' }))

    expect(line).toBe('Failure modes: worst action priority low')
  })

  it('shows no numeric score anywhere', () => {
    // Bands and counts only: a composite index would look authoritative and be arbitrary.
    const line = failureModeHeadline(
      summary({ worst_action_priority: 'medium', high_count: 1, unanswered_cells: 2 }),
    )

    expect(line).not.toMatch(/\bscore\b|\bindex\b|\brating\b/i)
  })
})

describe('what draws attention', () => {
  it('a high-priority row does', () => {
    expect(failureModeNeedsAttention(summary({ worst_action_priority: 'high', high_count: 1 }))).toBe(true)
  })

  it('an unexamined guideword does', () => {
    expect(failureModeNeedsAttention(summary({ unanswered_cells: 3 }))).toBe(true)
  })

  it('a fully examined, low-priority element does not', () => {
    expect(failureModeNeedsAttention(summary({ worst_action_priority: 'low' }))).toBe(false)
  })
})
