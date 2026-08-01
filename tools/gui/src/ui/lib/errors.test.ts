import { describe, expect, it } from 'vitest'
import { Data } from 'effect'
import {
  collectVerificationIssues,
  readApiErrorBody,
  hasVerificationErrors,
  readErrorMessage,
} from './errors'
import type { WriteVerification } from '../../domain/schemas/write-results'

const report = (fields: Partial<WriteVerification>): WriteVerification => ({
  valid: true,
  issues: [],
  ...fields,
})

const issue = (fields: Partial<WriteVerification['issues'][number]>) => ({
  severity: 'error' as const,
  code: '',
  message: '',
  ...fields,
})

class NetworkError extends Data.TaggedError('NetworkError')<{ readonly status: number; readonly message: string }> {}

describe('readErrorMessage', () => {
  it('unwraps a plain-string FastAPI detail envelope carried as a NetworkError message', () => {
    const error = new NetworkError({ status: 400, message: JSON.stringify({ detail: "unknown viewpoint slug 'x'" }) })
    expect(readErrorMessage(error)).toBe("unknown viewpoint slug 'x'")
  })

  it('reads `message` from an object detail it cannot decode as the envelope', () => {
    // A surface not yet on the envelope, or an envelope from a newer server. Either way the message is
    // prose a person can read, and the alternative is a JSON blob on the screen.
    const error = new NetworkError({
      status: 400,
      message: JSON.stringify({ detail: { code: 'something-newer', message: 'required parameter anchor is missing' } }),
    })
    expect(readErrorMessage(error)).toBe('required parameter anchor is missing')
  })

  it('returns a real Error prose message unchanged when it is not JSON', () => {
    expect(readErrorMessage(new Error('network unreachable'))).toBe('network unreachable')
  })

  it('returns a bare string error unchanged', () => {
    expect(readErrorMessage('boom')).toBe('boom')
  })

  it('falls back to a plain object with a string detail', () => {
    expect(readErrorMessage({ detail: 'plain object detail' })).toBe('plain object detail')
  })

  it('stringifies anything else as a last resort', () => {
    expect(readErrorMessage(42)).toBe('42')
  })
})

describe('readApiErrorBody', () => {
  it('decodes the published envelope a failed request carried', () => {
    const error = new NetworkError({
      status: 400,
      message: JSON.stringify({
        detail: {
          code: 'validation_error',
          message: 'max_hops must be at least 2',
          details: { field_errors: [{ field: 'query', message: 'max_hops must be at least 2' }] },
          request_id: 'r-9',
        },
      }),
    })
    const body = readApiErrorBody(error)
    expect(body?.code).toBe('validation_error')
    expect(body?.details).toEqual({ field_errors: [{ field: 'query', message: 'max_hops must be at least 2' }] })
  })

  it('is null for a plain-string detail envelope', () => {
    const error = new NetworkError({ status: 400, message: JSON.stringify({ detail: 'not typed' }) })
    expect(readApiErrorBody(error)).toBeNull()
  })

  it('is null for a real Error whose message is not JSON', () => {
    expect(readApiErrorBody(new Error('network unreachable'))).toBeNull()
  })

  it('is null for a body that is not the envelope', () => {
    const error = new NetworkError({ status: 400, message: JSON.stringify({ detail: { code: 'x' } }) })
    expect(readApiErrorBody(error)).toBeNull()
  })
})

describe('readErrorMessage never surfaces the raw envelope', () => {
  it('reads the envelope message rather than returning the JSON body', () => {
    // The defect this closes: `detail` is an object on every typed error, so the string-`detail`
    // unwrap never matched and the raw JSON was returned — and shown to the user.
    const error = new NetworkError({
      status: 400,
      message: JSON.stringify({
        detail: { code: 'bad_request', message: 'max_hops must be at least 2', details: null, request_id: 'r-1' },
      }),
    })
    expect(readErrorMessage(error)).toBe('max_hops must be at least 2')
  })
})

describe('collectVerificationIssues', () => {
  it('prefixes a message with its code', () => {
    const verification = report({
      valid: false,
      issues: [issue({ code: 'E335-fmt', message: 'unbalanced braces' })],
    })
    expect(collectVerificationIssues(verification)).toEqual(['E335-fmt: unbalanced braces'])
  })

  it('shows the message alone when the rule reported no code', () => {
    expect(collectVerificationIssues(report({ issues: [issue({ message: 'no code here' })] }))).toEqual([
      'no code here',
    ])
  })

  it('drops an issue carrying neither a code nor a message', () => {
    expect(collectVerificationIssues(report({ issues: [issue({})] }))).toEqual([])
  })

  it('is empty for a mutation that carries no report at all', () => {
    expect(collectVerificationIssues(null)).toEqual([])
  })
})

describe('hasVerificationErrors', () => {
  it('is true when the verifier said the content is invalid', () => {
    expect(hasVerificationErrors(report({ valid: false }))).toBe(true)
  })

  it('is true for a valid report that still carries warnings', () => {
    expect(
      hasVerificationErrors(report({ issues: [issue({ severity: 'warning', message: 'orphan' })] })),
    ).toBe(true)
  })

  it('is false for a clean report', () => {
    expect(hasVerificationErrors(report({}))).toBe(false)
  })

  it('is false when there is no report', () => {
    expect(hasVerificationErrors(null)).toBe(false)
  })
})
