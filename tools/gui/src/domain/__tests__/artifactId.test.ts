import { describe, expect, it } from 'vitest'
import { stableConnectionId, stableEntityId } from '../artifactId'

describe('stableEntityId', () => {
  it('strips the rename-volatile slug down to the stem', () => {
    expect(stableEntityId('FNC@1777390496.Z2rrfP.select-artifacts-for-promotion')).toBe('FNC@1777390496.Z2rrfP')
  })

  it('returns a stem-form id unchanged', () => {
    expect(stableEntityId('FNC@1777390496.Z2rrfP')).toBe('FNC@1777390496.Z2rrfP')
  })

  it('keeps a dash-adjacent random segment intact', () => {
    // Random segments like fduAv- / -RyIvn must not lose characters.
    expect(stableEntityId('VAL@1784845185.fduAv-.local-autonomy')).toBe('VAL@1784845185.fduAv-')
  })

  it('returns anything not entity-shaped as-is', () => {
    expect(stableEntityId('not-an-id')).toBe('not-an-id')
    expect(stableEntityId('')).toBe('')
  })
})

describe('stableConnectionId', () => {
  it('reduces both endpoints to stems and keeps the type', () => {
    expect(
      stableConnectionId('PRC@1.aB.some-process---FNC@2.cD.some-function@@archimate-composition'),
    ).toBe('PRC@1.aB---FNC@2.cD@@archimate-composition')
  })

  it('splits on the LAST @@ — a stray @@ in an endpoint round-trips without mangling', () => {
    expect(stableConnectionId('A@1.x---B@2.y@@weird@@type')).toBe('A@1.x---B@2.y@@weird@@type')
  })

  it('returns ids without a type marker unchanged', () => {
    expect(stableConnectionId('A@1.x@@archimate-serving')).toBe('A@1.x@@archimate-serving')
  })

  it('returns ids without an endpoint join unchanged', () => {
    expect(stableConnectionId('A@1.x---B@2.y')).toBe('A@1.x---B@2.y')
  })
})
