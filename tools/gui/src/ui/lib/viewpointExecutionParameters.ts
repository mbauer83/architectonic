/**
 * Pure helpers driving the execution-time parameter prompt: deriving a definition's
 * declared parameter signature from its stored envelope, deciding whether a prompt is
 * needed before the first execution, and coercing typed string inputs to the wire values
 * `POST /api/viewpoints/execute` expects.
 */

import { parameterFromMapping } from '../../domain/viewpointBindingsSerialization'
import type { ParameterValueType, QueryParameterNode } from '../../domain/viewpointBindings'
import type { ViewpointDefinitionEnvelope } from '../../domain'

const asRecord = (raw: unknown): Record<string, unknown> => raw as Record<string, unknown>

/** A draft value: a scalar's string, or a set-valued parameter's ordered members. */
export type ParameterDraftValue = string | readonly string[]
export type ParameterDraft = Record<string, ParameterDraftValue>

/** Blank scalar OR empty set — the "no value supplied" state, kept distinct from a
 * supplied-empty string so an unsupplied optional parameter is omitted from the wire body
 * (the backend's "missing" vs "supplied" distinction). */
export const isBlankDraftValue = (value: ParameterDraftValue | undefined): boolean =>
  value === undefined || (typeof value === 'string' ? value.trim() === '' : value.length === 0)

/** A definition's declared parameters, parsed from its stored `query.parameters` — empty
 * for a scope-only or unparameterized definition. */
export const parameterSignatureOf = (envelope: ViewpointDefinitionEnvelope | undefined): readonly QueryParameterNode[] => {
  const query = envelope?.query
  if (query == null || typeof query !== 'object') return []
  const parameters = asRecord(query).parameters
  return Array.isArray(parameters) ? parameters.map(parameterFromMapping) : []
}

/** A prompt is needed exactly when at least one required parameter has no default —
 * an all-optional or all-defaulted signature executes immediately, same as today. */
export const needsParameterPrompt = (signature: readonly QueryParameterNode[]): boolean =>
  signature.some((p) => p.required && isBlankDraftValue(defaultDraftValue(p)))

/** A parameter's default as a draft value — a set parameter's is its member array (copied so
 * the draft never aliases the declaration), a scalar's is its default string. */
const defaultDraftValue = (parameter: QueryParameterNode): ParameterDraftValue =>
  parameter.cardinality === 'many'
    ? [...(typeof parameter.default === 'string' ? [] : parameter.default)]
    : (typeof parameter.default === 'string' ? parameter.default : '')

/** Typed drafts, one per declared parameter, seeded from each parameter's own default —
 * the prompt/toolbar's own local form state. */
export const initialParameterDraft = (signature: readonly QueryParameterNode[]): ParameterDraft =>
  Object.fromEntries(signature.map((p) => [p.name, defaultDraftValue(p)]))

/** Seed a draft from already-bound WIRE values (the canonical values an execution ran with),
 * falling back to each parameter's default for any the caller did not supply — used by the
 * always-on toolbar so it opens reflecting the current result, and a reloaded shared URL
 * reproduces it. A set parameter's members are copied to strings; a scalar is stringified. */
export const draftFromWireValues = (
  signature: readonly QueryParameterNode[],
  values: Readonly<Record<string, unknown>>,
): ParameterDraft => {
  const draft = initialParameterDraft(signature)
  for (const parameter of signature) {
    if (!(parameter.name in values)) continue
    const value = values[parameter.name]
    draft[parameter.name] = Array.isArray(value) ? value.map(String) : String(value)
  }
  return draft
}

/** A required parameter still missing a value in the current draft — drives the submit
 * button's disabled state and which fields to flag. */
export const missingRequiredParameters = (
  signature: readonly QueryParameterNode[],
  draft: Readonly<ParameterDraft>,
): readonly QueryParameterNode[] => signature.filter((p) => p.required && isBlankDraftValue(draft[p.name]))

/** Coerces one typed string draft value to the wire shape `execute`'s `parameters` body
 * expects — `entity-id`/`string`/`slug` pass through as strings (an artifact id is a
 * string), `integer`/`number` parse numerically, `boolean` from a checkbox's own
 * true/false string, `date` stays an ISO date string (the wire format already used
 * elsewhere in this codebase). Non-numeric numeric input yields `null` (caller's own
 * required-field check already prevents submitting an empty one; a malformed one is
 * caught by save-mode... execution-mode validation server-side, never silently coerced
 * to 0). */
export const coerceParameterValue = (valueType: ParameterValueType, raw: string): unknown => {
  if (valueType === 'boolean') return raw === 'true'
  if (valueType === 'integer') {
    const parsed = Number.parseInt(raw, 10)
    return Number.isNaN(parsed) ? null : parsed
  }
  if (valueType === 'number') {
    const parsed = Number.parseFloat(raw)
    return Number.isNaN(parsed) ? null : parsed
  }
  return raw
}

/** The full wire-shaped `parameters` body from a draft — omits a parameter entirely when
 * its draft value is blank (an unsupplied optional parameter, not an explicit empty
 * string), matching the backend's "missing" vs. "supplied-empty" distinction. A set-valued
 * parameter sends its member array verbatim (the backend canonicalizes order + dedup). */
export const parametersToWireValues = (
  signature: readonly QueryParameterNode[],
  draft: Readonly<ParameterDraft>,
): Record<string, unknown> => {
  const result: Record<string, unknown> = {}
  for (const parameter of signature) {
    const value = draft[parameter.name]
    if (isBlankDraftValue(value)) continue
    result[parameter.name] = typeof value === 'string'
      ? coerceParameterValue(parameter.valueType, value)
      : [...value]
  }
  return result
}
