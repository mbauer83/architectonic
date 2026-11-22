import type { Effect } from 'effect'
import type { DiagramComposition } from './diagramWriteBodies'
import type { Extent } from '../domain/layout/geometry'
import type {
  DiagramLayoutPatchResult, DrawingNode, LayoutGeometry,
} from '../domain/schemas/diagramLayoutGeometry'
import type { RepoError } from './repositoryErrors'

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

/** Arranging a diagram: the picture it is arranged on, resized shapes drawn anew, and the layout write. */
export interface DiagramLayoutRepository {
  readonly previewLayoutGeometry: (diagramId: string, composition: DiagramComposition) => Effect.Effect<LayoutGeometry, RepoError>
  readonly readLayoutGeometry: (diagramId: string) => Effect.Effect<LayoutGeometry, RepoError>
  readonly drawResizedShapes: (
    diagramId: string, shapes: readonly ShapeToDraw[],
  ) => Effect.Effect<readonly DrawingNode[], RepoError>
  readonly patchLayout: (
    diagramId: string, patch: LayoutPatch, dryRun: boolean,
  ) => Effect.Effect<DiagramLayoutPatchResult, RepoError>
}
