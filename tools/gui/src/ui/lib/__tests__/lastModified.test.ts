import { describe, expect, it } from 'vitest'
import { NO_STAMP, formatLastModified, lastModifiedTitle } from '../lastModified'

describe('formatLastModified', () => {
  it('renders a canonical UTC instant as date and time-of-day', () => {
    expect(formatLastModified('2026-07-24T09:15:00Z')).toBe('2026-07-24 09:15')
  })

  it('keeps a pre-migration date-only stamp as a bare date', () => {
    expect(formatLastModified('2026-01-01')).toBe('2026-01-01')
  })

  it('shows a placeholder for an unstamped artifact', () => {
    expect(formatLastModified(null)).toBe(NO_STAMP)
    expect(formatLastModified(undefined)).toBe(NO_STAMP)
    expect(formatLastModified('')).toBe(NO_STAMP)
  })

  it('shows an unrecognised value verbatim rather than hiding it', () => {
    expect(formatLastModified('whenever')).toBe('whenever')
  })
})

describe('lastModifiedTitle', () => {
  it('keeps the exact stored instant available on hover', () => {
    expect(lastModifiedTitle('2026-07-24T09:15:00Z')).toBe('Last modified 2026-07-24T09:15:00Z (UTC)')
  })

  it('explains an empty cell', () => {
    expect(lastModifiedTitle(null)).toBe('No modification stamp recorded')
  })
})
