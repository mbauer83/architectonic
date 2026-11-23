import { Effect, Schema } from 'effect'
import type { DiagramLayoutRepository } from '../../ports/DiagramLayoutRepository'
import {
  DiagramLayoutGeometrySchema, DiagramLayoutPatchResultSchema, ShapeDrawingsSchema,
} from '../../domain/schemas/diagramLayoutGeometry'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, fetchJson, patchJson, postJson } from './httpTransport'

const layoutUrl = (diagramId: string, part = ''): string =>
  buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/layout${part}`)

/** The arranging half of the HTTP adapter, over a diagram's layout routes. */
export const diagramLayoutMethods = (): DiagramLayoutRepository => ({
  listDiagramElementTypes: diagramType => fetchJson(
    buildUrl(`/diagram-types/${encodeURIComponent(diagramType)}/entity-types`),
    Schema.Struct({items: Schema.Array(Schema.Struct({artifact_type: Schema.String, domain: Schema.String}))}),
  ).pipe(Effect.map(response => response.items)),
  previewLayoutGeometry: (diagramId, body) =>
    postJson(layoutUrl(diagramId, '/geometry/preview'), body, DiagramLayoutGeometrySchema),
  readLayoutGeometry: (diagramId) => fetchJson(layoutUrl(diagramId, '/geometry'), DiagramLayoutGeometrySchema),
  drawResizedShapes: (diagramId, shapes) =>
    postJson(layoutUrl(diagramId, '/preview'), { shapes }, ShapeDrawingsSchema).pipe(
      Effect.map((answer) => answer.drawings),
    ),
  patchLayout: (diagramId, patch, dryRun) =>
    patchJson(layoutUrl(diagramId), { patch, dry_run: dryRun }, DiagramLayoutPatchResultSchema),
})
