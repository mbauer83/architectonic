import { describe, it, expect } from 'vitest'
import { reasonHint, effectiveOcclusionState, projectionByItemId } from '../EditDiagramView.helpers'
import type { ProjectedOccurrence, ViewpointProjection } from '../../../domain'

const occurrence = (overrides: Partial<ProjectedOccurrence> = {}): ProjectedOccurrence => ({
  item_id: 'X@1.a.x', item_kind: 'entity', state: 'visible', membership: 'primary', reasons: [], style: {},
  ...overrides,
})

describe('reasonHint', () => {
  it('returns null when there are no reasons (fully matching)', () => {
    expect(reasonHint([])).toBeNull()
  })

  it('maps a single reason to a readable hint', () => {
    expect(reasonHint(['out_of_scope'])).toBe('Excluded: out of scope for the applied viewpoint')
  })

  it('maps criteria_mismatch', () => {
    expect(reasonHint(['criteria_mismatch'])).toBe("Excluded: does not match the viewpoint's query criteria")
  })

  it('joins multiple reasons (e.g. a connection whose endpoint is also excluded)', () => {
    expect(reasonHint(['endpoint_excluded', 'out_of_scope'])).toBe(
      'Excluded: one of its endpoints is excluded; out of scope for the applied viewpoint',
    )
  })
})

describe('effectiveOcclusionState', () => {
  it('visible stays visible regardless of the hide toggle', () => {
    expect(effectiveOcclusionState(occurrence({ state: 'visible' }), false)).toBe('visible')
    expect(effectiveOcclusionState(occurrence({ state: 'visible' }), true)).toBe('visible')
  })

  it('ghosted stays ghosted when hide-instead-of-ghost is off', () => {
    expect(effectiveOcclusionState(occurrence({ state: 'ghosted' }), false)).toBe('ghosted')
  })

  it('ghosted renders hidden when hide-instead-of-ghost is on', () => {
    expect(effectiveOcclusionState(occurrence({ state: 'ghosted' }), true)).toBe('hidden')
  })
})

describe('projectionByItemId', () => {
  it('returns an empty map for a null projection', () => {
    expect(projectionByItemId(null).size).toBe(0)
  })

  it('indexes items by item_id', () => {
    const projection: ViewpointProjection = {
      applied: true, target: 'diagram',
      items: [occurrence({ item_id: 'A' }), occurrence({ item_id: 'B', item_kind: 'connection' })],
    }
    const index = projectionByItemId(projection)
    expect(index.get('A')?.item_id).toBe('A')
    expect(index.get('B')?.item_kind).toBe('connection')
    expect(index.size).toBe(2)
  })
})
