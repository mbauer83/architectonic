import { describe, expect, it } from 'vitest'
import { executionErrorDisplay, parameterNameFromPath } from './viewpointExecutionErrorText'
import type { TypedApiError } from './errors'

describe('parameterNameFromPath', () => {
  it('extracts the parameter name from a parameters/<name> path', () => {
    expect(parameterNameFromPath('parameters/anchor')).toBe('anchor')
  })

  it('is null for a non-parameter path', () => {
    expect(parameterNameFromPath('query')).toBeNull()
  })
})

describe('executionErrorDisplay', () => {
  const error = (overrides: Partial<TypedApiError>): TypedApiError => ({ code: 'x', path: 'query', message: 'boom', ...overrides })

  it('names the missing parameter', () => {
    const display = executionErrorDisplay(error({ code: 'missing-parameter', path: 'parameters/anchor', message: 'missing-parameter: anchor' }))
    expect(display.title).toBe('Missing a required parameter')
    expect(display.detail).toContain('anchor')
  })

  it('names the unknown parameter', () => {
    const display = executionErrorDisplay(error({ code: 'unknown-parameter', path: 'parameters/bogus', message: 'unknown-parameter: bogus' }))
    expect(display.title).toBe('Unknown parameter supplied')
    expect(display.detail).toContain('bogus')
  })

  it('names the type-mismatched parameter', () => {
    const display = executionErrorDisplay(error({ code: 'parameter-type-mismatch', path: 'parameters/limit', message: 'parameter-type-mismatch: limit' }))
    expect(display.title).toBe("Parameter value doesn't match its type")
    expect(display.detail).toContain('limit')
  })

  it('gives an actionable timeout message', () => {
    const display = executionErrorDisplay(error({ code: 'execution-timeout', message: 'viewpoint execution exceeded 5.0s' }))
    expect(display.title).toBe('This took too long to execute')
    expect(display.detail).toContain('narrowing the query')
  })

  it('gives an actionable derivation-limit message', () => {
    const display = executionErrorDisplay(error({ code: 'derivation-limit', message: 'exceeded max hops' }))
    expect(display.title).toBe('Derived-relationship traversal limit exceeded')
    expect(display.detail).toContain('hop bound')
  })

  it('gives an actionable binding-cardinality message', () => {
    const display = executionErrorDisplay(error({ code: 'binding-cardinality-violation', message: 'binding "x" resolved to 3 entities' }))
    expect(display.title).toBe('A binding matched the wrong number of items')
    expect(display.detail).toContain('declared as exactly-one')
  })

  it('falls back to a generic-but-still-distinct state for an unrecognized code', () => {
    const display = executionErrorDisplay(error({ code: 'something-new', message: 'unrecognized failure' }))
    expect(display.title).toBe('Execution failed')
    expect(display.detail).toBe('unrecognized failure')
  })
})
