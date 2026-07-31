import { describe, expect, it } from 'vitest'
import { Data } from 'effect'
import {
  collectVerificationIssues,
  extractTypedApiError,
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

  it('unwraps the message field of a typed {code, path, message} detail envelope', () => {
    const error = new NetworkError({
      status: 400,
      message: JSON.stringify({ detail: { code: 'parameter-missing', path: 'parameters/anchor', message: 'required parameter anchor is missing' } }),
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

describe('extractTypedApiError', () => {
  it('extracts the structured error for a typed detail envelope', () => {
    const error = new NetworkError({
      status: 400,
      message: JSON.stringify({ detail: { code: 'derivation-limit', path: 'query', message: 'too many hops', expected: '5', found: '9' } }),
    })
    expect(extractTypedApiError(error)).toEqual({ code: 'derivation-limit', path: 'query', message: 'too many hops', expected: '5', found: '9' })
  })

  it('is null for a plain-string detail envelope', () => {
    const error = new NetworkError({ status: 400, message: JSON.stringify({ detail: 'not typed' }) })
    expect(extractTypedApiError(error)).toBeNull()
  })

  it('is null for a real Error whose message is not JSON', () => {
    expect(extractTypedApiError(new Error('network unreachable'))).toBeNull()
  })

  it('is null for a non-string, non-Error value', () => {
    expect(extractTypedApiError({ detail: { code: 'x', path: 'y', message: 'z' } })).toBeNull()
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
