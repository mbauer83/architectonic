/**
 * Per-code actionable prose for a failed viewpoint execution — the PLAN's failure-mode contract
 * requires each of these to render as "a distinct, actionable error state", never a generic flat
 * message. Pure so it's testable without mounting Vue.
 *
 * Reads the **published error envelope** (`ErrorBody`), which is what the surface actually sends.
 * It used to read a parallel `{code, path, message}` body the viewpoint routes invented: the error
 * handler reduced that to a status-derived code and dropped the path, so the `path` check failed,
 * every execution failure arrived here as `null`, and the screen showed the raw JSON envelope under
 * a bare "Execution failed". Every branch below was unreachable in production while its unit tests
 * passed against hand-built literals.
 *
 * A rejected input is `validation_error` now, with the input named in `field_errors[].field` — the
 * same shape every other rejected field on this surface uses, including FastAPI's own 422.
 */

import type { ErrorBody } from '../../domain/schemas/errors'

/** The parameter name a `parameters.<name>` field path names, or `null` for anything else. */
export const parameterNameFromField = (field: string): string | null => {
  const match = /^parameters\.(.+)$/.exec(field)
  return match ? match[1] : null
}

export interface ExecutionErrorDisplay {
  readonly title: string
  readonly detail: string
}

/** The first rejected field's path, or `null` when the failure carried no field errors. */
const rejectedField = (error: ErrorBody): string | null => {
  const details = error.details
  if (details === undefined || details === null || !('field_errors' in details)) return null
  return details.field_errors[0]?.field ?? null
}

const inputRejection = (error: ErrorBody): ExecutionErrorDisplay => {
  const field = rejectedField(error)
  const parameter = field === null ? null : parameterNameFromField(field)
  if (parameter !== null) {
    return { title: 'A parameter was not accepted', detail: `${error.message} (parameter: ${parameter}).` }
  }
  if (field === 'presentation') {
    return { title: 'That presentation was not accepted', detail: error.message }
  }
  return { title: 'That query was not accepted', detail: error.message }
}

const renderLimit = (error: ErrorBody): ExecutionErrorDisplay => {
  const details = error.details
  const bounds =
    details !== undefined && details !== null && 'max_entities' in details
      ? ` It has ${details.entity_count} entities and the renderer takes ${details.max_entities}.`
      : ''
  return { title: 'Result too large for diagram rendering', detail: `${error.message}${bounds}` }
}

const cardinality = (error: ErrorBody): ExecutionErrorDisplay => {
  const details = error.details
  const which =
    details !== undefined && details !== null && 'binding' in details
      ? ` Binding “${details.binding}” declared ${details.expected} and resolved to ${details.found} — check its criteria.`
      : ' Check the binding’s criteria.'
  return { title: 'A binding matched the wrong number of items', detail: `${error.message}${which}` }
}

export const executionErrorDisplay = (error: ErrorBody): ExecutionErrorDisplay => {
  if (error.code === 'validation_error') return inputRejection(error)
  if (error.code === 'traversal_time_budget_exceeded') {
    return {
      title: 'The traversal exceeded its budget',
      detail:
        `${error.message} Narrow the query — fewer criteria, a tighter concept scope, a lower hop `
        + 'bound or a lower limit — then run it again.',
    }
  }
  if (error.code === 'diagram_render_limit') return renderLimit(error)
  if (error.code === 'binding_cardinality_violation') return cardinality(error)
  return { title: 'Execution failed', detail: error.message }
}
