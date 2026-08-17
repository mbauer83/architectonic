import { describe, it, expect } from 'vitest'
import {
  ENFORCED_FORMATS,
  formatValidationError,
  inputTypeForFormat,
  placeholderForFormat,
} from './attributeValidation'

/**
 * The form's answers about a declared format have to be the backend's answers. Where these
 * disagree the reader is told a value is fine and the write path then refuses it, which is worse
 * than no client check at all — so the cases below are the same cases
 * `tests/domain/test_attribute_format_facet.py` states against `validate_against_schema`.
 */
describe('format-aware editing', () => {
  it('names the formats the backend enforces, and only those', () => {
    expect([...ENFORCED_FORMATS]).toEqual(['uri', 'date'])
  })

  it('leaves a value alone when its attribute declares no format', () => {
    expect(formatValidationError(undefined, 'anything at all')).toBeNull()
    expect(formatValidationError('', 'anything at all')).toBeNull()
  })

  it('says nothing about a format nothing enforces', () => {
    // Such a declaration cannot reach a running backend — startup refuses it — so the form has
    // nothing useful to say about one and must not invent a rule of its own.
    expect(formatValidationError('email', 'not an email')).toBeNull()
  })

  describe('uri', () => {
    it('accepts an absolute reference', () => {
      expect(formatValidationError('uri', 'https://tracker.example/PROJ-1')).toBeNull()
    })

    it('accepts a relative reference to an artifact, which is why the control is not type=url', () => {
      const reference = '../../../model/motivation/requirement/REQ@1712870400.Po1Qw3.coherent.md'
      expect(formatValidationError('uri', reference)).toBeNull()
      expect(inputTypeForFormat('uri')).toBeNull()
    })

    it('rejects prose that addresses nothing', () => {
      expect(formatValidationError('uri', 'see the wiki, somewhere'))
        .toBe('Must be a link or a path, with no spaces')
    })

    it('hints at what it wants, having no native control to say it', () => {
      expect(placeholderForFormat('uri')).toBe('https://… or a relative path')
    })
  })

  describe('date', () => {
    it('renders the browser control whose value is already the enforced shape', () => {
      expect(inputTypeForFormat('date')).toBe('date')
      expect(placeholderForFormat('date')).toBeNull()
    })

    it('accepts a calendar date', () => {
      expect(formatValidationError('date', '2026-08-17')).toBeNull()
    })

    it('rejects another ordering of the same day', () => {
      expect(formatValidationError('date', '17/08/2026')).toBe('Must be a date, as YYYY-MM-DD')
    })

    it('rejects a value that is shaped like a date and is not one', () => {
      expect(formatValidationError('date', '2026-13-45')).toBe('Must be a date, as YYYY-MM-DD')
    })
  })

  it('leaves an empty value to the required check, so a blank field says one thing', () => {
    expect(formatValidationError('uri', '')).toBeNull()
    expect(formatValidationError('date', '   ')).toBeNull()
  })
})
