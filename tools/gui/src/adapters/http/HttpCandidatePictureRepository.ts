import { Effect } from 'effect'
import type { CandidatePictureRepository } from '../../ports/CandidatePictureRepository'
import { DiagramLayoutGeometrySchema, ShapeDrawingsSchema } from '../../domain/schemas/diagramLayoutGeometry'
import { PictureContextSchema } from '../../domain/schemas/diagrams'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, fetchJson, postJson } from './httpTransport'

const pictureUrl = (id: string, part = ''): string =>
  buildUrl(`/change-sets/${encodeIdentitySegment(id)}/picture${part}`)

/** The candidate picture's half of the HTTP adapter. */
export const candidatePictureMethods = (): CandidatePictureRepository => ({
  readCandidatePictureContext: (id) => fetchJson(pictureUrl(id, '/context'), PictureContextSchema),
  readCandidatePicture: (id) => fetchJson(pictureUrl(id), DiagramLayoutGeometrySchema),
  previewCandidatePicture: (id, composition) =>
    postJson(pictureUrl(id, '/preview'), composition, DiagramLayoutGeometrySchema),
  drawCandidatePictureShapes: (id, shapes) =>
    postJson(pictureUrl(id, '/shapes/preview'), { shapes }, ShapeDrawingsSchema)
      .pipe(Effect.map((answer) => answer.drawings)),
})
