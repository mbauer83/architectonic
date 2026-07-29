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

export const collectVerificationIssues = (verification: unknown): string[] => {
  if (!isRecord(verification)) {
    return []
  }
  const { issues } = verification
  if (!Array.isArray(issues)) {
    return []
  }
  return issues.flatMap((issue) => {
    if (!isRecord(issue)) {
      return []
    }
    const code = typeof issue.code === 'string' ? issue.code : ''
    const message = typeof issue.message === 'string' ? issue.message : ''
    if (!code && !message) {
      return []
    }
    return [code ? `${code}: ${message}` : message]
  })
}

export const hasVerificationErrors = (verification: unknown): boolean => {
  if (!isRecord(verification)) {
    return false
  }
  // Check valid flag first (primary indicator)
  if (verification.valid === false) {
    return true
  }
  // Also check for issues array (backward compatibility and detailed errors)
  const { issues } = verification
  return Array.isArray(issues) && issues.length > 0
}

export const formatEffectError = (e: unknown): string => {
  if (isRecord(e) && e._tag === 'NotFoundError' && typeof e.id === 'string') {
    return `Not found: ${e.id}`
  }
  return readErrorMessage(e)
}
