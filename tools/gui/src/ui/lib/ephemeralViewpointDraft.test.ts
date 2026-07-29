import { beforeEach, describe, expect, it } from 'vitest'
import {
  hasStagedEphemeralViewpointDraft, stageEphemeralViewpointDraft, takeEphemeralViewpointDraft,
} from './ephemeralViewpointDraft'
import { mkQuery } from '../../domain/viewpointCriteria'
import { mkPresentation } from '../../domain/viewpointPresentation'

describe('ephemeral viewpoint draft hand-off', () => {
  // Module-level singleton: drain any residue so tests do not leak into one another.
  beforeEach(() => { takeEphemeralViewpointDraft() })

  it('starts empty', () => {
    expect(hasStagedEphemeralViewpointDraft()).toBe(false)
    expect(takeEphemeralViewpointDraft()).toBeNull()
  })

  it('stages a draft and consumes it exactly once (Save as… hand-off is single-use)', () => {
    const draft = { query: mkQuery(), presentation: mkPresentation('table') }
    stageEphemeralViewpointDraft(draft)
    expect(hasStagedEphemeralViewpointDraft()).toBe(true)

    expect(takeEphemeralViewpointDraft()).toBe(draft)

    // A second /viewpoints/new open must NOT be contaminated by the prior hand-off.
    expect(hasStagedEphemeralViewpointDraft()).toBe(false)
    expect(takeEphemeralViewpointDraft()).toBeNull()
  })

  it('a fresh stage replaces an unconsumed one', () => {
    const first = { query: mkQuery(), presentation: null }
    const second = { query: mkQuery(), presentation: mkPresentation('matrix') }
    stageEphemeralViewpointDraft(first)
    stageEphemeralViewpointDraft(second)
    expect(takeEphemeralViewpointDraft()).toBe(second)
  })
})
