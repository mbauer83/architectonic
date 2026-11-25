import { Effect, Schema } from 'effect'
import type { DiagramLayoutRepository } from '../../ports/DiagramLayoutRepository'
import {
  DiagramLayoutGeometrySchema, DiagramLayoutPatchResultSchema, ShapeDrawingsSchema, SurroundPlacementSchema,
} from '../../domain/schemas/diagramLayoutGeometry'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { lensParams } from '../../domain/readingLens'
import { buildUrl, fetchJson, patchJson, postJson } from './httpTransport'

const layoutUrl = (diagramId: string, part = '', params?: Parameters<typeof buildUrl>[1]): string =>
  buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/layout${part}`, params)

/** The arranging half of the HTTP adapter, over a diagram's layout routes. */
export const diagramLayoutMethods = (): DiagramLayoutRepository => ({
  listDiagramElementTypes: diagramType => fetchJson(
    buildUrl(`/diagram-types/${encodeURIComponent(diagramType)}/entity-types`),
    Schema.Struct({items: Schema.Array(Schema.Struct({artifact_type: Schema.String, domain: Schema.String}))}),
  ).pipe(Effect.map(response => response.items)),
  previewLayoutGeometry: (diagramId, body, lens) =>
    postJson(layoutUrl(diagramId, '/geometry/preview', lens && lensParams(lens)), body, DiagramLayoutGeometrySchema),
  readLayoutGeometry: (diagramId, lens) =>
    fetchJson(layoutUrl(diagramId, '/geometry', lens && lensParams(lens)), DiagramLayoutGeometrySchema),
  placeSurround: (diagramId, placement) =>
    postJson(layoutUrl(diagramId, '/surround/preview'), placement, SurroundPlacementSchema).pipe(
      Effect.map((answer) => answer.moves),
    ),
  drawResizedShapes: (diagramId, shapes) =>
    postJson(layoutUrl(diagramId, '/preview'), { shapes }, ShapeDrawingsSchema).pipe(
      Effect.map((answer) => answer.drawings),
    ),
  patchLayout: (diagramId, patch, dryRun) =>
    patchJson(layoutUrl(diagramId), { patch, dry_run: dryRun }, DiagramLayoutPatchResultSchema),
})
