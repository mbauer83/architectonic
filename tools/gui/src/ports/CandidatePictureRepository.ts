import type { Effect } from 'effect'
import type { GeometryComposition } from './diagramWriteBodies'
import type { ShapeToDraw } from './DiagramLayoutRepository'
import type { RepoError } from './repositoryErrors'
import type { DrawingNode, LayoutGeometry } from '../domain/schemas/diagramLayoutGeometry'
import type { PictureContext } from '../domain/schemas/diagrams'

/**
 * The picture a candidate is sketched on, with the candidate as the subject: a diagram editor's reads, served
 * for a candidate that needs no stored diagram. It starts from the stored diagram the candidate is drawn on,
 * from a view generated from what it reads over, or from nothing. Every call writes nothing.
 */
export interface CandidatePictureRepository {
  /** Where the candidate's picture starts, with what the model relates it to and what lies near it. */
  readonly readCandidatePictureContext: (id: string) => Effect.Effect<PictureContext, RepoError>
  /** The picture as it starts; the empty picture for a candidate that reads over nothing yet. */
  readonly readCandidatePicture: (id: string) => Effect.Effect<LayoutGeometry, RepoError>
  /** An edit session's composition drawn over where the picture starts. */
  readonly previewCandidatePicture: (
    id: string, composition: GeometryComposition,
  ) => Effect.Effect<LayoutGeometry, RepoError>
  /** Resized shapes drawn anew by the composer. */
  readonly drawCandidatePictureShapes: (
    id: string, shapes: readonly ShapeToDraw[],
  ) => Effect.Effect<readonly DrawingNode[], RepoError>
}
