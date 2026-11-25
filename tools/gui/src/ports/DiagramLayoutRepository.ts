import type { Effect } from 'effect'
import type { GeometryComposition } from './diagramWriteBodies'
import type { Extent } from '../domain/layout/geometry'
import type {
  DiagramLayoutPatchResult,
  DrawingNode,
  LayoutGeometry,
} from '../domain/schemas/diagramLayoutGeometry'
import type { RepoError } from './repositoryErrors'
import type { ReadingLens } from '../domain/readingLens'

/** A shape resized on the canvas: PlantUML's drawing of it, where that was drawn, and where it goes. */
export interface ShapeToDraw {
  readonly drawing: DrawingNode
  readonly box: boolean
  readonly drawn: Extent
  readonly to: Extent
}

/**
 * One entry of a layout patch: what it becomes (`null` removes it) and what it was read as (`null`
 * for absent). The server refuses the whole patch where an entry's `based_on` no longer holds.
 */
export interface LayoutEntryChange {
  readonly value: unknown
  readonly based_on?: unknown
}

/** Changes to a diagram's layout block, by section (`elements`, `boxes`, `relations`, `z`) and key. */
export type LayoutPatch = Readonly<Record<string, Readonly<Record<string, LayoutEntryChange | null>>>>

/**
 * Where a diagram being arranged is now, to place what is drawn round it: the parts' extents and what the
 * diagram occupied as PlantUML drew them, and its shapes, line courses and line labels now.
 */
export interface SurroundPlacement {
  readonly drawn: Extent
  readonly parts: readonly Extent[]
  readonly shapes: readonly Extent[]
  readonly courses: readonly (readonly (readonly [number, number])[])[]
  readonly labels: readonly Extent[]
}

/** Arranging a diagram: the picture it is arranged on, resized shapes drawn anew, and the layout write. */
export interface DiagramLayoutRepository {
  readonly listDiagramElementTypes: (
    diagramType: string,
  ) => Effect.Effect<readonly { artifact_type: string; domain: string }[], RepoError>
  /** The picture of an unsaved composition; under *lens*, drawn as the reader is reading it. */
  readonly previewLayoutGeometry: (
    diagramId: string,
    composition: GeometryComposition,
    lens?: ReadingLens,
  ) => Effect.Effect<LayoutGeometry, RepoError>
  /** The picture a diagram is arranged on; under *lens*, drawn as the reader is reading it (owner, 11-25). */
  readonly readLayoutGeometry: (diagramId: string, lens?: ReadingLens) => Effect.Effect<LayoutGeometry, RepoError>
  /** How far each part drawn round the diagram moves, by the composer's rule, in the order given. */
  readonly placeSurround: (
    diagramId: string,
    placement: SurroundPlacement,
  ) => Effect.Effect<readonly (readonly [number, number])[], RepoError>
  readonly drawResizedShapes: (
    diagramId: string,
    shapes: readonly ShapeToDraw[],
  ) => Effect.Effect<readonly DrawingNode[], RepoError>
  readonly patchLayout: (
    diagramId: string,
    patch: LayoutPatch,
    dryRun: boolean,
  ) => Effect.Effect<DiagramLayoutPatchResult, RepoError>
}
