import { describe, it, expect } from 'vitest'
import { Schema } from 'effect'
import {
  ErrorEnvelopeSchema,
  isRetryable,
  viewpointReferencedDetails,
  type ErrorBody,
} from './errors'

/**
 * The error envelope's decoder and its two narrowing helpers.
 *
 * These are the only executable lines in `errors.ts` — everything else is schema declaration, held
 * against the generated OpenAPI types by `openapi.contract.test-d.ts`. That type-level file cannot
 * cover the two helpers, because what they do is decide at runtime; the module sat at 0% as a result,
 * which is what took `src/domain/**` branch coverage under its floor.
 *
 * Both helpers exist so that no component re-derives the narrowing. The envelope nests `details`
 * rather than discriminating the union by `code`, so narrowing needs a shape check as well as the
 * code — and getting that subtly wrong in one view is the failure they prevent.
 */

const body = (over: Partial<ErrorBody> = {}): ErrorBody => ({
  code: 'bad_request',
  message: 'no',
  request_id: 'req-1',
  ...over,
})

describe('isRetryable', () => {
  it('is false when there are no details to read it from', () => {
    expect(isRetryable(body())).toBe(false)
    expect(isRetryable(body({ details: null }))).toBe(false)
  })

  it('is false when the details carry no retryable flag', () => {
    expect(isRetryable(body({ details: { field_errors: [] } }))).toBe(false)
  })

  it('distinguishes a retryable denial from a permanent one', () => {
    expect(isRetryable(body({ details: { reason_code: 'locked', retryable: true } }))).toBe(true)
    expect(isRetryable(body({ details: { reason_code: 'locked', retryable: false } }))).toBe(false)
  })
})

describe('viewpointReferencedDetails', () => {
  const referencers = [{ artifact_id: 'ARC@1.a.b', target_kind: 'diagram' as const }]

  it('returns the referencers when the refusal is that one', () => {
    const found = viewpointReferencedDetails(
      body({ code: 'viewpoint_referenced', details: { slug: 'v', referencers } }),
    )
    expect(found?.referencers).toEqual(referencers)
  })

  it('is null for another code, even carrying a details object of the same shape', () => {
    expect(
      viewpointReferencedDetails(body({ code: 'conflict', details: { slug: 'v', referencers } })),
    ).toBeNull()
  })

  it('is null when the right code carries no details, or details of another shape', () => {
    expect(viewpointReferencedDetails(body({ code: 'viewpoint_referenced' }))).toBeNull()
    expect(
      viewpointReferencedDetails(body({ code: 'viewpoint_referenced', details: null })),
    ).toBeNull()
    expect(
      viewpointReferencedDetails(
        body({ code: 'viewpoint_referenced', details: { field_errors: [] } }),
      ),
    ).toBeNull()
  })
})

describe('the error envelope decodes what the backend serves', () => {
  it('accepts an envelope with no details at all', () => {
    const decoded = Schema.decodeUnknownSync(ErrorEnvelopeSchema)({
      detail: { code: 'not_found', message: 'gone', request_id: 'req-2' },
    })
    expect(decoded.detail.code).toBe('not_found')
  })

  it('accepts each details variant the union declares a decoder for', () => {
    for (const details of [
      { field_errors: [{ field: 'name', message: 'required' }] },
      { entity_count: 900, max_entities: 400 },
      { binding: 'subject', expected: 'exactly one', found: 3 },
      { capability: 'assurance', remedy: 'enable it' },
    ]) {
      const decoded = Schema.decodeUnknownSync(ErrorEnvelopeSchema)({
        detail: { code: 'bad_request', message: 'no', request_id: 'req-3', details },
      })
      expect(decoded.detail.details).toEqual(details)
    }
  })

  it('refuses a code the server cannot send — the literal union is the point', () => {
    expect(() =>
      Schema.decodeUnknownSync(ErrorEnvelopeSchema)({
        detail: { code: 'teapot', message: 'no', request_id: 'req-4' },
      }),
    ).toThrow()
  })
})
