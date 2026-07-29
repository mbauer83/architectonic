/**
 * The optional ad-hoc execution source that lets the four result views (exploration, table,
 * matrix, diagram) render an UNSAVED query + presentation (§5.3) instead of resolving a saved
 * slug. When a view receives an `adHoc`, it executes `request` (an inline `{query,presentation}`,
 * or a `{slug,presentation}` ephemeral override) and uses `presentation` for its presentation-
 * dependent computeds — reusing the same evaluator, projection, and renderer as the saved path.
 */

import type { ViewpointExecutionRequest } from '../../domain'
import type { PresentationNode } from '../../domain/viewpointPresentation'

export interface AdHocExecution {
  readonly request: ViewpointExecutionRequest
  readonly presentation: PresentationNode | null
}
