import type { Effect } from 'effect'
import type { DiagramAttributePanel } from '../domain/schemas/diagrams'
import type { ReadingLens } from '../domain/readingLens'
import type { RepoError } from './repositoryErrors'

/**
 * Reading a diagram's picture: the image, and what it can be read *by*.
 *
 * Its own file for the reason `ScratchpadRepository` is one — `ModelRepository` reached the 350-line
 * limit — and this is a seam rather than an arbitrary cut. Both methods serve one surface, the diagram
 * page's reading controls, and they are the only two reads in the whole port that answer to a lens:
 * everything else asks for an artifact and gets the artifact, while these two ask "show me this
 * diagram the way I am looking at it" and "what ways are there".
 */
export interface DiagramReadingRepository {
  /** The rendered diagram. Without a lens this is the authored image, served from disk; with one the
   * server re-renders, because the colouring and the printed values live in the PlantUML body. */
  readonly getDiagramSvg: (id: string, lens?: ReadingLens) => Effect.Effect<string, RepoError>
  /** What this diagram's own entities can be coloured by and print: the types and specializations it
   * draws, and per type the attributes they declare. */
  readonly getDiagramAttributePanel: (id: string) => Effect.Effect<DiagramAttributePanel, RepoError>
}
