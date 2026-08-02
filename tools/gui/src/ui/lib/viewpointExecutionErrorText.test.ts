import { describe, expect, it } from 'vitest'
import { executionErrorDisplay, parameterNameFromField } from './viewpointExecutionErrorText'
import type { ErrorBody } from '../../domain/schemas/errors'

/**
 * These assertions used to be built from a `{code, path, message}` literal the surface never sent, so
 * every branch under test was unreachable in production while this file stayed green. They are built
 * from the published envelope now — the shape `readApiErrorBody` decodes.
 */

const envelope = (overrides: Partial<ErrorBody>): ErrorBody =>
  ({ code: 'bad_request', message: 'boom', details: null, request_id: 'r-1', ...overrides })

const rejected = (field: string, message: string): ErrorBody =>
  envelope({ code: 'validation_error', message, details: { field_errors: [{ field, message }] } })

describe('parameterNameFromField', () => {
  it('extracts the parameter name from a parameters.<name> field path', () => {
    expect(parameterNameFromField('parameters.anchor')).toBe('anchor')
  })

  it('is null for a field that is not a parameter', () => {
    expect(parameterNameFromField('query')).toBeNull()
  })
})

describe('executionErrorDisplay', () => {
  it('names the rejected parameter', () => {
    // The wire message is a sentence about the expectation now; the parameter name is read from
    // `field`, which is why dropping the retired code word from the prose changed nothing here.
    const display = executionErrorDisplay(
      rejected('parameters.bogus', 'bogus: the query declares no such parameter'),
    )
    expect(display.title).toBe('A parameter was not accepted')
    expect(display.detail).toContain('bogus')
  })

  it('distinguishes a rejected query from a rejected presentation', () => {
    expect(executionErrorDisplay(rejected('query', 'max_hops must be at least 2')).title)
      .toBe('That query was not accepted')
    expect(executionErrorDisplay(rejected('presentation', 'unknown representation')).title)
      .toBe('That presentation was not accepted')
  })

  it('gives an actionable message for an exceeded traversal budget', () => {
    // One code for both the wall-clock timeout and the derivation bound: they are the same budget,
    // and `traversal_time_budget_exceeded` already meant this before the viewpoint routes existed.
    const display = executionErrorDisplay(
      envelope({ code: 'traversal_time_budget_exceeded', message: 'viewpoint execution exceeded 5.0s' }),
    )
    expect(display.title).toBe('The traversal exceeded its budget')
    expect(display.detail).toContain('hop bound')
  })

  it('reports both render bounds, so the reader knows how much to narrow by', () => {
    const display = executionErrorDisplay(
      envelope({
        code: 'diagram_render_limit',
        message: 'too large for diagram rendering.',
        details: { entity_count: 900, max_entities: 400 },
      }),
    )
    expect(display.title).toBe('Result too large for diagram rendering')
    expect(display.detail).toContain('900')
    expect(display.detail).toContain('400')
  })

  it('names which binding matched the wrong number of items', () => {
    const display = executionErrorDisplay(
      envelope({
        code: 'binding_cardinality_violation',
        message: "binding 'one' requires exactly one result, got 2",
        details: { binding: 'one', expected: 'exactly one', found: 2 },
      }),
    )
    expect(display.title).toBe('A binding matched the wrong number of items')
    expect(display.detail).toContain('one')
    expect(display.detail).toContain('2')
  })

  it('falls back to the flat message for an unrecognised code', () => {
    expect(executionErrorDisplay(envelope({ code: 'internal_error', message: 'nope' })))
      .toEqual({ title: 'Execution failed', detail: 'nope' })
  })

  it('survives a code whose details are absent', () => {
    // `traversal_time_budget_exceeded` declares none, and the two that do can still arrive without
    // them if a producer omits them — no branch may assume they are there.
    expect(executionErrorDisplay(envelope({ code: 'diagram_render_limit', message: 'too large.' })).detail)
      .toBe('too large.')
    expect(executionErrorDisplay(envelope({ code: 'binding_cardinality_violation', message: 'bad count.' })).detail)
      .toContain('criteria')
  })
})
