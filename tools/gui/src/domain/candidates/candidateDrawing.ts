/**
 * A candidate drawn as it composes, over the picture it is read on (owner, 2026-11-22: stressors apply
 * to the naive architecture, so what they are ticked on is the naive, not the model beneath it).
 *
 * The commands are the canvas editor's own (`model.element.create`, `.rename`, `model.relation.create`),
 * so the same composition (`composeCanvas`) and the same preview draw a candidate whether it is
 * sketched or read. They are read off the candidate's composed view against what the diagram draws,
 * not off its operations: a stacked candidate draws everything its stack changes, whatever base its
 * reader compares it with. What the candidate removes is not taken off the picture — it stays drawn,
 * for the reader's marks to show it as a ghost.
 */
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import type { CandidateComparison } from '../schemas/candidates'
import { stableConnectionId, stableEntityId } from '../artifactId'
import { chosenIds, creationCommand, drawnEnds, relationCommand } from './candidateCanvas'

/** What the picture draws already, and the relations the model holds among what it draws. */
export interface DrawnContent {
  readonly entities: readonly { readonly artifact_id: string; readonly name: string }[]
  readonly connections: readonly { readonly artifact_id: string }[]
  /** Relations the model holds that the picture leaves undrawn: not the candidate's to add. */
  readonly undrawn: readonly { readonly artifact_id: string }[]
}

/** A candidate composed down its stack: its entities and relations as they would stand. */
export type ComposedView = CandidateComparison['view']

const text = (value: unknown): string => (typeof value === 'string' ? value : '')

/** The commands that draw *view*'s changes over a picture drawing *drawn*. */
export const drawnCommands = (view: ComposedView, drawn: DrawnContent): readonly CanvasCommand[] => {
  const chosen = chosenIds(view)
  const names = new Map(drawn.entities.map((one) => [stableEntityId(one.artifact_id), one.name]))
  const creates = view.entities.flatMap((one) => (one.artifact_id ? [creationCommand(one.artifact_id, one.fields)] : []))
  const renames = view.entities.flatMap((one): CanvasCommand[] => {
    const was = names.get(stableEntityId(one.id))
    const now = text(one.fields.name)
    return !one.artifact_id && was !== undefined && now !== '' && now !== was
      ? [{ op: 'model.element.rename', artifact_id: one.id, name: now }] : []
  })
  const drawnAs = drawnEnds([...drawn.entities, ...creates].map((one) => one.artifact_id), chosen)
  const held = new Set([...drawn.connections, ...drawn.undrawn].map((one) => stableConnectionId(one.artifact_id)))
  const relations = view.connections.flatMap((one) => {
    const command = relationCommand(one, drawnAs)
    return command && !held.has(stableConnectionId(command.artifact_id)) ? [command] : []
  })
  return [...creates, ...renames, ...relations]
}
