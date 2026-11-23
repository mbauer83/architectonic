import type { Effect } from 'effect'
import type { DiagramAttributePanel } from '../domain/schemas/diagrams'
import type { DiagramTypeMemberItem } from '../domain/schemas/authoring-guidance'
import type { DerivedNeighbor } from '../domain/schemas/entities'
import type { ReadingLens } from '../domain/readingLens'
import type { RepoError } from './repositoryErrors'

/**
 * Reading a diagram: its picture, what the picture can be read *by*, and what a reader follows out of it.
 *
 * Its own file for the reason `ScratchpadRepository` is one — `ModelRepository` reached the 350-line
 * limit — and this is a seam rather than an arbitrary cut. Every method serves one surface, the diagram
 * page in view mode: the picture and its lens, and the two reads the diagram reader (B97) adds — which
 * relation types have a direction to follow, and what the model derives beyond what is drawn.
 */
export interface DiagramReadingRepository {
  /** The rendered diagram. Without a lens this is the authored image, served from disk; with one the
   * server re-renders, because the colouring and the printed values live in the PlantUML body. */
  readonly getDiagramSvg: (id: string, lens?: ReadingLens) => Effect.Effect<string, RepoError>
  /** What this diagram's own entities can be coloured by and print: the types and specializations it
   * draws, and per type the attributes they declare. */
  readonly getDiagramAttributePanel: (id: string) => Effect.Effect<DiagramAttributePanel, RepoError>
  /** The connection types a diagram kind accepts. Each item is open: `symmetric` says the type has no
   * direction, so the reader follows it both ways. */
  readonly getDiagramTypeConnectionTypes: (
    diagramType: string,
  ) => Effect.Effect<readonly DiagramTypeMemberItem[], RepoError>
  /** The relationships the model derives from an entity through intermediate elements, certain and
   * potential, within the server's configured derivation bound. */
  readonly getDerivedNeighbors: (entityId: string) => Effect.Effect<readonly DerivedNeighbor[], RepoError>
}
