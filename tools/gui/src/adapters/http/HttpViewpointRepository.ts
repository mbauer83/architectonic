import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { ModelRepository } from '../../ports/ModelRepository'
import {
  CriteriaCatalogSchema,
  DiagramViewpointProjectionSchema,
  ViewpointDefinitionListSchema,
  ViewpointDiagramResultSchema,
  ViewpointExecutionResultSchema,
  ViewpointPersistResultSchema,
  ViewpointPinsSchema,
  ViewpointProjectionSchema,
  ViewpointReferencerListSchema,
  ViewpointSummarizeResultSchema,
} from '../../domain/schemas/viewpoints'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import {
  buildUrl,
  deleteNoContent,
  deleteReq,
  fetchJson,
  fetchWithTimeout,
  postJson,
  putJson,
} from './httpTransport'

/**
 * The viewpoint half of the HTTP adapter: definitions, execution, projections and pins.
 *
 * Split out because the composed adapter had grown past the file-size limit and this is the surface
 * with the clearest seam — nothing here touches an artifact directly. Typed by `Pick` from the port
 * rather than by a second interface, so the signatures still have exactly one declaration.
 */
export const viewpointMethods = (): Pick<
  ModelRepository,
  | 'getViewpointProjection'
  | 'listViewpointDefinitions'
  | 'getCriteriaCatalog'
  | 'executeViewpoint'
  | 'executeViewpointProjection'
  | 'executeViewpointDiagram'
  | 'summarizeViewpointQuery'
  | 'exportViewpointCsv'
  | 'createViewpointDefinition'
  | 'replaceViewpointDefinition'
  | 'previewDeleteViewpointDefinition'
  | 'deleteViewpointDefinition'
  | 'getViewpointReferencers'
  | 'getViewpointPins'
  | 'setViewpointPins'
> => ({
  getViewpointProjection: (diagramId: string) =>
    fetchJson(
      buildUrl(`/diagrams/${encodeURIComponent(diagramId)}/viewpoint-projection`),
      DiagramViewpointProjectionSchema,
    ),
  listViewpointDefinitions: () =>
    fetchJson(buildUrl('/viewpoints'), ViewpointDefinitionListSchema).pipe(Effect.map((r) => r.viewpoints)),
  getCriteriaCatalog: () => fetchJson(buildUrl('/viewpoints/criteria-catalog'), CriteriaCatalogSchema),
  executeViewpoint: (request) =>
    postJson(buildUrl('/viewpoints/execute'), request, ViewpointExecutionResultSchema),
  executeViewpointProjection: (request) =>
    postJson(buildUrl('/viewpoints/execute-projection'), request, ViewpointProjectionSchema),
  executeViewpointDiagram: (request) =>
    postJson(buildUrl('/viewpoints/execute-diagram'), request, ViewpointDiagramResultSchema),
  summarizeViewpointQuery: (query: unknown) =>
    postJson(buildUrl('/viewpoints/summarize'), { query }, ViewpointSummarizeResultSchema).pipe(
      Effect.map((r) => r.summary),
    ),
  exportViewpointCsv: (body) =>
    Effect.tryPromise({
      try: async () => {
        const resp = await fetchWithTimeout(buildUrl('/viewpoints/export-csv'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!resp.ok) {
          const text = await resp.text().catch(() => resp.statusText)
          throw new NetworkError({ status: resp.status, message: text })
        }
        return resp.text()
      },
      catch: (e) => (e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) })),
    }),
  createViewpointDefinition: (body) => postJson(buildUrl('/viewpoints'), body, ViewpointPersistResultSchema),
  replaceViewpointDefinition: (slug, body) =>
    putJson(buildUrl(`/viewpoints/${encodeIdentitySegment(slug)}`), body, ViewpointPersistResultSchema),
  previewDeleteViewpointDefinition: (slug) =>
    deleteReq(
      buildUrl(`/viewpoints/${encodeIdentitySegment(slug)}`, { dry_run: true }),
      ViewpointPersistResultSchema,
    ),
  deleteViewpointDefinition: (slug) =>
    deleteNoContent(buildUrl(`/viewpoints/${encodeIdentitySegment(slug)}`)),
  getViewpointReferencers: (slug: string) =>
    fetchJson(buildUrl(`/viewpoints/${encodeURIComponent(slug)}/referencers`), ViewpointReferencerListSchema).pipe(
      Effect.map((r) => r.referencers),
    ),
  getViewpointPins: () => fetchJson(buildUrl('/viewpoints/pins'), ViewpointPinsSchema),
  setViewpointPins: (slugs: readonly string[]) =>
    putJson(buildUrl('/viewpoints/pins'), { slugs: [...slugs] }, ViewpointPinsSchema),
})
