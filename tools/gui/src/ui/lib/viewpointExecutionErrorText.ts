/**
 * Per-code actionable prose for a typed viewpoint-execution error (`TypedApiError`) — the
 * PLAN's failure-mode contract requires each of these to render as "a distinct, actionable
 * error state", never a generic flat message. Pure so it's testable without mounting Vue.
 */

import type { TypedApiError } from './errors'

/** The parameter name a `parameters/<name>` execution-error path names, or `null` for a
 * path that doesn't follow that convention (e.g. `query`). */
export const parameterNameFromPath = (path: string): string | null => {
  const match = /^parameters\/(.+)$/.exec(path)
  return match ? match[1] : null
}

export interface ExecutionErrorDisplay {
  readonly title: string
  readonly detail: string
}

const PARAMETER_TITLES: Readonly<Record<string, string>> = {
  'missing-parameter': 'Missing a required parameter',
  'unknown-parameter': 'Unknown parameter supplied',
  'parameter-type-mismatch': "Parameter value doesn't match its type",
}

export const executionErrorDisplay = (error: TypedApiError): ExecutionErrorDisplay => {
  const parameterName = parameterNameFromPath(error.path)
  if (parameterName !== null && error.code in PARAMETER_TITLES) {
    return { title: PARAMETER_TITLES[error.code], detail: `${error.message} (parameter: ${parameterName}).` }
  }
  if (error.code === 'execution-timeout') {
    return {
      title: 'This took too long to execute',
      detail: `${error.message} Try narrowing the query — fewer criteria, a tighter concept scope, or a lower limit — then run it again.`,
    }
  }
  if (error.code === 'derivation-limit') {
    return {
      title: 'Derived-relationship traversal limit exceeded',
      detail: `${error.message} Reduce the hop bound or narrow the derived-traversal criteria, then run it again.`,
    }
  }
  if (error.code === 'diagram-render-limit') {
    return {
      title: 'Result too large for diagram rendering',
      detail: error.message,
    }
  }
  if (error.code === 'binding-cardinality-violation') {
    return {
      title: 'A binding matched the wrong number of items',
      detail: `${error.message} A binding declared as exactly-one (or zero-or-one) resolved to a different count — check its criteria.`,
    }
  }
  return { title: 'Execution failed', detail: error.message }
}
