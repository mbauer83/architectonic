import { describe, it, expect } from 'vitest'
import { EDIT_QUARANTINE_TITLE, EDIT_REQUIRED_TITLE, editBlockedReason } from './entityEditBlocking'

describe('editBlockedReason', () => {
  it('gives no reason when nothing blocks the save', () => {
    expect(editBlockedReason(false, false)).toBeUndefined()
  })

  it('reports missing required properties', () => {
    expect(editBlockedReason(false, true)).toBe(EDIT_REQUIRED_TITLE)
  })

  it('reports quarantine', () => {
    expect(editBlockedReason(true, false)).toBe(EDIT_QUARANTINE_TITLE)
  })

  it('prefers quarantine over the in-form reason', () => {
    // Filling the required fields in would not unblock the save, so saying so would misdirect.
    expect(editBlockedReason(true, true)).toBe(EDIT_QUARANTINE_TITLE)
  })
})
