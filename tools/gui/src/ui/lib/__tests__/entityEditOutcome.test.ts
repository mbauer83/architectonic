import { describe, expect, it } from 'vitest'
import {
  editOutcome,
  editOutcomeTitle,
  savedIdIsTheArtifact,
  savedMessage,
} from '../entityEditBlocking'

describe('what saving an edit does', () => {
  it('writes here for content this repository owns', () => {
    expect(editOutcome(false, false)).toBe('writes-here')
  })

  it('records a change for promoted content, which is the ordinary case', () => {
    // The affordance was hidden entirely on these, so the only interface most people use offered
    // no way to reach the feature and no explanation either.
    expect(editOutcome(true, false)).toBe('records-a-change')
  })

  it('writes upstream in admin mode, which is the one that needs the warning', () => {
    expect(editOutcome(true, true)).toBe('writes-upstream')
  })

  it('admin mode changes nothing for content this repository owns', () => {
    expect(editOutcome(false, true)).toBe('writes-here')
  })
})

describe('what the control promises before it is clicked', () => {
  it('says nothing about an ordinary edit', () => {
    expect(editOutcomeTitle('writes-here')).toBeUndefined()
  })

  it('says the edit is recorded here, not that anyone has been asked to look', () => {
    // It promised "awaiting review", which is not what clicking Edit does: the change is recorded
    // as a draft, and only submitting it puts it in front of anyone.
    expect(editOutcomeTitle('records-a-change')).toMatch(/recorded as a local change/)
    expect(editOutcomeTitle('records-a-change')).not.toMatch(/awaiting review/)
  })

  it('keeps naming admin mode, which is where the write does land upstream', () => {
    expect(editOutcomeTitle('writes-upstream')).toMatch(/admin mode/)
  })
})

describe('where a save leaves you', () => {
  it('follows a renamed artifact, which is what the returned id is for', () => {
    expect(savedIdIsTheArtifact('writes-here')).toBe(true)
    expect(savedIdIsTheArtifact('writes-upstream')).toBe(true)
  })

  it('does not follow the id a recorded change answers with', () => {
    // That id names the *change* — an internal artifact nobody should be shown. Following it
    // navigated the reader straight into one, which is the thing references are hidden to avoid.
    expect(savedIdIsTheArtifact('records-a-change')).toBe(false)
  })

  it('does not say "saved" when nothing was saved here, nor that review has begun', () => {
    expect(savedMessage('records-a-change')).toBe('Change recorded')
    expect(savedMessage('writes-here')).toBe('Entity saved')
  })
})
