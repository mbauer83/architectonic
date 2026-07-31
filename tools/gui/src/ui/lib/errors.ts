import { Either, Schema } from 'effect'
import { type ErrorBody, ErrorBodySchema } from '../../domain/schemas/errors'
import type { WriteVerification } from '../../domain/schemas/write-results'

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

/** The structured `{code, path, message}` body FastAPI sends for a typed HTTPException
 * detail (`ViewpointParameterError`/`BindingCardinalityError`/`DerivationLimitError`/
 * `ViewpointExecutionTimeoutError`, and others) — distinct from a plain-string `detail`,
 * which every other HTTPException still sends. */
export interface TypedApiError {
  readonly code: string
  readonly path: string
  readonly message: string
  readonly expected?: string | null
  readonly found?: string | null
}

const isTypedApiError = (value: unknown): value is TypedApiError =>
  isRecord(value) && typeof value.code === 'string' && typeof value.path === 'string' && typeof value.message === 'string'

/** The raw JSON text a failed `fetch` call's body carries, whichever adapter shape wraps
 * it — an `Error`-like value's `.message` (the network adapter's convention: the response
 * body text, not a human sentence) or a bare string. `null` for anything else (a real
 * thrown `Error` with prose, a plain object, ...). */
const rawResponseText = (error: unknown): string | null => {
  if (typeof error === 'string') return error
  if (error instanceof Error && error.message) return error.message
  return null
}

/** The typed `{code, path, message}` error a viewpoint-execution (or similarly typed)
 * endpoint sent, decoded from the raw response body — `null` when the response wasn't
 * JSON, wasn't a FastAPI `{"detail": ...}` envelope, or carried a plain-string `detail`
 * (most HTTPExceptions). Callers that only need prose should use `readErrorMessage`. */
export const extractTypedApiError = (error: unknown): TypedApiError | null => {
  const raw = rawResponseText(error)
  if (raw === null) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    return isRecord(parsed) && isTypedApiError(parsed.detail) ? parsed.detail : null
  } catch {
    return null
  }
}

/**
 * The typed error envelope a failed request carried, decoded — or null when it carried none.
 *
 * The transport throws the raw response body as an `Error`'s `.message`, so the envelope is already
 * in hand; this decodes it with the same schema the contract assertions hold against the generated
 * OpenAPI types. Callers use it to branch on `code` and read `details`, which is the whole reason
 * the server sends a code instead of a sentence.
 */
export const readApiErrorBody = (error: unknown): ErrorBody | null => {
  const raw = rawResponseText(error)
  if (raw === null) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!isRecord(parsed)) return null
    const decoded = Schema.decodeUnknownEither(ErrorBodySchema)(parsed.detail)
    return Either.isRight(decoded) ? decoded.right : null
  } catch {
    return null
  }
}

export const readErrorMessage = (error: unknown): string => {
  const typed = extractTypedApiError(error)
  if (typed) return typed.message
  const raw = rawResponseText(error)
  if (raw !== null) {
    // The network adapters throw the raw HTTP response body text as an Error's `.message`
    // (not prose) — try to unwrap a FastAPI `{"detail": "..."}` envelope before falling
    // back to the raw text verbatim, so a real error still reads like an error.
    try {
      const parsed = JSON.parse(raw) as unknown
      if (isRecord(parsed) && typeof parsed.detail === 'string' && parsed.detail) return parsed.detail
    } catch {
      /* not JSON (a real thrown Error's own prose message) — use it as-is below */
    }
    return raw
  }
  if (isRecord(error)) {
    const detail = error.detail
    if (typeof detail === 'string' && detail) {
      return detail
    }
  }
  return String(error)
}

/**
 * The verification report's issues as display lines.
 *
 * Took `unknown` and re-derived the shape a field at a time, because the server's `verification` was
 * an undeclared object — the decoder could promise nothing, so every reader checked everything. It is
 * `WriteVerificationSchema` now, and the only case left to handle is a mutation that carries no report.
 */
export const collectVerificationIssues = (
  verification: WriteVerification | null | undefined,
): string[] =>
  (verification?.issues ?? []).flatMap((issue) =>
    issue.code || issue.message
      ? [issue.code ? `${issue.code}: ${issue.message}` : issue.message]
      : [],
  )

export const hasVerificationErrors = (
  verification: WriteVerification | null | undefined,
): boolean => {
  if (verification === null || verification === undefined) {
    return false
  }
  // `valid` is the verifier's own verdict; a warning-only report is invalid to a preview that must
  // decide whether to offer the write, so a non-empty issue list counts either way.
  return !verification.valid || verification.issues.length > 0
}

export const formatEffectError = (e: unknown): string => {
  if (isRecord(e) && e._tag === 'NotFoundError' && typeof e.id === 'string') {
    return `Not found: ${e.id}`
  }
  return readErrorMessage(e)
}

/**
 * A failed response's message, read from the shared error envelope.
 *
 * Every REST failure answers `{"detail": {code, message, details, request_id}}`, and a rejected
 * write carries its field errors in `details.field_errors`. Joining them beats showing "HTTP 422":
 * the point of the typed envelope is that a form can point at the field that failed.
 *
 * Takes an already-parsed body rather than a thrown error, for the components that call `fetch`
 * directly — `readApiErrorBody` is the Effect-adapter path to the same envelope.
 */
export const describeEnvelope = (body: Record<string, unknown>, status: number): string => {
  const detail = body.detail
  if (typeof detail !== 'object' || detail === null) return `HTTP ${status}`
  const { message, details } = detail as { message?: unknown; details?: unknown }
  const fieldErrors =
    typeof details === 'object' && details !== null && 'field_errors' in details
      ? (details as { field_errors: { field: string; message: string }[] }).field_errors
      : null
  if (fieldErrors && fieldErrors.length > 0) {
    return fieldErrors.map((e) => `${e.field}: ${e.message}`).join('; ')
  }
  return typeof message === 'string' && message ? message : `HTTP ${status}`
}
