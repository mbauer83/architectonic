/**
 * Where an edit session reads the picture it arranges and draws: a stored diagram, or a candidate.
 *
 * One editor serves both (`useDiagramEditing`); only where its picture comes from differs. A diagram's picture
 * is the stored diagram's, and what the session changes is saved into it. A candidate is the subject of its own
 * picture: it starts from the stored diagram the candidate is drawn on, or from a view generated from what it
 * reads over, or from nothing — and what the session changes is recorded in the candidate as it is made, never
 * saved into a diagram, so a candidate's source names no diagram to save into.
 */
import type { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { GeometryComposition } from '../../ports/diagramWriteBodies'
import type { ShapeToDraw } from '../../ports/DiagramLayoutRepository'
import type { RepoError } from '../../ports/repositoryErrors'
import type { NotFoundError, PictureContext } from '../../domain'
import type { DrawingNode, LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ReadingLens } from '../../domain/readingLens'

export interface PictureSource {
  /** What the picture starts from: the elements and relations it draws, and the relations it leaves undrawn. */
  readonly context: () => Effect.Effect<PictureContext, RepoError | NotFoundError>
  /** The picture as it starts; under *lens*, drawn as the reader is reading it. */
  readonly read: (lens?: ReadingLens) => Effect.Effect<LayoutGeometry, RepoError>
  /** A session's composition drawn over where the picture starts, writing nothing. */
  readonly preview: (composition: GeometryComposition, lens?: ReadingLens) => Effect.Effect<LayoutGeometry, RepoError>
  /** Resized shapes drawn anew by the composer. */
  readonly reshape: (shapes: readonly ShapeToDraw[]) => Effect.Effect<readonly DrawingNode[], RepoError>
  /** The stored diagram a save writes into; absent where what is drawn is recorded as it is made. */
  readonly savesInto?: () => string
}

/** The picture of the stored diagram *diagramId*, which a save writes into. */
export const diagramPicture = (
  svc: Pick<ModelService, 'getDiagramContext' | 'readLayoutGeometry' | 'previewLayoutGeometry' | 'drawResizedShapes'>,
  diagramId: () => string,
): PictureSource => ({
  context: () => svc.getDiagramContext(diagramId()),
  read: (lens) => svc.readLayoutGeometry(diagramId(), lens),
  preview: (composition, lens) => svc.previewLayoutGeometry(diagramId(), composition, lens),
  reshape: (shapes) => svc.drawResizedShapes(diagramId(), shapes),
  savesInto: diagramId,
})

/** The picture the candidate *candidateId* is sketched on, with the candidate as its subject. */
export const candidatePicture = (
  svc: Pick<ModelService,
    'readCandidatePictureContext' | 'readCandidatePicture' | 'previewCandidatePicture' | 'drawCandidatePictureShapes'>,
  candidateId: () => string,
): PictureSource => ({
  context: () => svc.readCandidatePictureContext(candidateId()),
  read: () => svc.readCandidatePicture(candidateId()),
  preview: (composition) => svc.previewCandidatePicture(candidateId(), composition),
  reshape: (shapes) => svc.drawCandidatePictureShapes(candidateId(), shapes),
})

/** The stored diagram *source* saves into; refused for a source that records as it is sketched (a candidate). */
export const savedInto = (source: PictureSource): string => {
  if (!source.savesInto) throw new Error('This picture is recorded as it is sketched; there is nothing to save.')
  return source.savesInto()
}
