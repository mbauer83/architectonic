import { describe, it, expect } from 'vitest'
import {
  PREVIEW_FIRST_TITLE,
  QUARANTINE_TITLE,
  REQUIRED_TITLE,
  createBlockedReason,
  previewBlockedReason,
} from '../EntityCreateView.helpers'

describe('previewBlockedReason', () => {
  it('gives no reason when preview is available', () => {
    expect(previewBlockedReason(false, false)).toBeUndefined()
  })

  it('reports missing required properties', () => {
    expect(previewBlockedReason(false, true)).toBe(REQUIRED_TITLE)
  })

  it('prefers quarantine — filling the form in would not unblock it', () => {
    expect(previewBlockedReason(true, true)).toBe(QUARANTINE_TITLE)
  })
})

describe('createBlockedReason', () => {
  it('gives no reason once preview is clean and nothing is missing', () => {
    expect(createBlockedReason(false, true, false)).toBeUndefined()
  })

  it('asks for a preview first', () => {
    expect(createBlockedReason(false, false, false)).toBe(PREVIEW_FIRST_TITLE)
  })

  it('reports missing required properties once preview is clean', () => {
    expect(createBlockedReason(false, true, true)).toBe(REQUIRED_TITLE)
  })

  it('prefers quarantine over both in-form reasons', () => {
    expect(createBlockedReason(true, false, true)).toBe(QUARANTINE_TITLE)
  })
})
