/**
 * What a declared attribute means to an authoring form: which control renders it, and why a value
 * is not yet acceptable.
 *
 * `attributeValidationError` is the whole rule, in one place, because it had been in two — the
 * component computed it and its test file re-implemented it under a comment saying so, which is a
 * copy that agrees until one of them changes. The component now renders this and the test now
 * tests it.
 *
 * `format` says what a value *addresses*, rather than what shape it has, and that changes two
 * things about editing it: which control to render, and what counts as a value worth submitting.
 * Both live here so a second surface cannot answer them differently — the entity form, the
 * connection-metadata form and the array item editor all render through `TypedPropertyInput`, and
 * every one of them reaches this.
 *
 * **The backend is authoritative.** `validate_against_schema` enforces the same two formats and
 * refuses a write regardless of what a form allowed, and startup refuses a schema declaring a
 * format nothing checks. What is here is the early answer, so a reader is told before they submit
 * rather than after — the messages are deliberately the same shape as the server's.
 */

/** The formats the backend enforces. A declaration naming anything else is refused at startup. */
export const ENFORCED_FORMATS = ['uri', 'date'] as const
export type EnforcedFormat = (typeof ENFORCED_FORMATS)[number]

const isEnforced = (format: string | undefined): format is EnforcedFormat =>
  (ENFORCED_FORMATS as readonly string[]).includes(format ?? '')

/**
 * The `<input type>` a format asks for, or null to leave the control as the type chose it.
 *
 * `date` maps to the browser's own date control, whose value is `YYYY-MM-DD` — the shape the
 * backend enforces, so the picker cannot produce a value the write path then refuses.
 *
 * `uri` deliberately stays a text input. `type="url"` requires a scheme, and a reference to an
 * artifact this repository manages is written relative, exactly as every other link to it is; a
 * url control would refuse the case the facet exists to carry.
 */
export const inputTypeForFormat = (format: string | undefined): 'date' | null =>
  format === 'date' ? 'date' : null

/** A hint for a control that has no native affordance for its format. */
export const placeholderForFormat = (format: string | undefined): string | null =>
  format === 'uri' ? 'https://… or a relative path' : null

/**
 * Why this value does not satisfy its declared format, or null when it does.
 *
 * An empty value is never a format error: whether it may be empty is what `required` answers, and
 * reporting both for one blank field says the same thing twice.
 */
export const formatValidationError = (
  format: string | undefined,
  value: string,
): string | null => {
  if (!isEnforced(format)) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (format === 'uri') {
    return /\s/.test(trimmed) ? 'Must be a link or a path, with no spaces' : null
  }
  return isCalendarDate(trimmed) ? null : 'Must be a date, as YYYY-MM-DD'
}

/** `YYYY-MM-DD`, and a real day — `2026-13-45` matches the shape and is not a date. */
const isCalendarDate = (value: string): boolean => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}


/** A declared pattern is a server-side schema's regex; an unparseable one judges nothing. */
const patternMatches = (pattern: string, value: string): boolean => {
  try {
    return new RegExp(pattern).test(value)
  } catch {
    return true
  }
}

/**
 * Why *value* is not yet an acceptable value for *descriptor*, or null when it is.
 *
 * Mirrors what the write path enforces, in the order a reader can act on: whether anything is
 * there at all, then whether it is the declared type, then the declared vocabulary, then the
 * declared bounds, then what it addresses. The backend refuses regardless — this exists so the
 * refusal arrives before the submit rather than after it.
 *
 * Length and pattern were served and bound to the control and reported by nothing: the browser's
 * own validity state never reaches the form's error line, so an over-long or non-matching value
 * looked accepted until the write refused it.
 */
export const attributeValidationError = (
  descriptor: AttributeShape,
  value: string,
  required = false,
): string | null => {
  if (required && !value.trim()) return 'Required'
  if (!value) return null
  if (descriptor.type === 'integer' && !/^-?[0-9]+$/.test(value.trim())) {
    return 'Must be a whole number'
  }
  if (descriptor.type === 'number' && Number.isNaN(Number(value.trim()))) return 'Must be a number'
  const allowed = descriptor.enum
  if (allowed?.length && !allowed.includes(value)) {
    return `Must be one of: ${allowed.join(', ')}`
  }
  const c = descriptor.constraints
  if (c?.minLength !== undefined && value.length < c.minLength) {
    return `Must be at least ${c.minLength} characters`
  }
  if (c?.maxLength !== undefined && value.length > c.maxLength) {
    return `Must be at most ${c.maxLength} characters`
  }
  if (c?.pattern && !patternMatches(c.pattern, value)) return `Must match ${c.pattern}`
  return formatValidationError(descriptor.format, value)
}

/** The part of an attribute descriptor a validation answer depends on. */
export interface AttributeShape {
  readonly type: string
  readonly format?: string
  readonly enum?: readonly string[]
  readonly constraints?: {
    readonly minLength?: number
    readonly maxLength?: number
    readonly pattern?: string
  }
}
