import { Effect } from 'effect'
import type { ViewpointDefinitionEnvelope, ViewpointSummary } from '../../domain/schemas/viewpoints'

/** Project a viewpoint list envelope (from the dedicated `/api/viewpoints` source) onto the
 * lighter ViewpointSummary the pickers consume. Viewpoint discovery lives in the viewpoints
 * API, not authoring guidance — this keeps the two concerns separate while giving the pickers
 * the slug/name/scope they need. `purpose`/`content` may arrive as a string or array. */
const asArray = (value: string | readonly string[] | undefined): string[] =>
  value === undefined ? [] : typeof value === 'string' ? [value] : [...value]

export const viewpointSummaryFromEnvelope = (env: ViewpointDefinitionEnvelope): ViewpointSummary => ({
  slug: env.slug,
  version: env.version,
  name: env.name,
  description: env.description ?? '',
  purpose: asArray(env.purpose),
  content: asArray(env.content),
  scope: env.scope ?? env.scope_summary,
})

/** Fetch the viewpoint picker summaries from the dedicated /api/viewpoints listing (shared by the
 * diagram-authoring views); an empty list on failure keeps the picker non-blocking. */
export const loadViewpointSummaries = (
  listing: Effect.Effect<readonly ViewpointDefinitionEnvelope[], unknown>,
): Promise<ViewpointSummary[]> =>
  Effect.runPromise(listing).then((defs) => defs.map(viewpointSummaryFromEnvelope)).catch(() => [])
