/**
 * A candidate applied as a target state, as its page reads it: where its target state stands in the model
 * (read off the candidate's record), and the sentences its two confirmations open with. What is written,
 * and whether it may be, is the server's; nothing here judges an operation.
 */
import { Either, Schema } from 'effect'
import { stableEntityId } from '../artifactId'
import { type TargetStateIds, TargetStateIdsSchema } from '../schemas/candidates'
import { operationLabel } from './candidateApply'

/** The record's key for the target state, as the recorded form spells it. */
const RECORDED_KEY = 'target-state'

const decode = Schema.decodeUnknownEither(TargetStateIdsSchema)

/** Where *record*'s target state stands in the model; null when it is not in the model as one. */
export const targetStateOf = (record: Readonly<Record<string, unknown>>): TargetStateIds | null => {
  const recorded = record[RECORDED_KEY]
  if (recorded === undefined || recorded === null) return null
  // `copies` and `added` are left out of the record when empty.
  const decoded = decode({ copies: {}, added: {}, ...(recorded as object) })
  return Either.isRight(decoded) ? decoded.right : null
}

const plural = (count: number, one: string, many = `${one}s`): string => `${count} ${count === 1 ? one : many}`

/** What applying as a target state writes, in one sentence, from the ids a dry run answered. */
export const targetSentence = (ids: TargetStateIds, operations: number): string => {
  const added = Object.keys(ids.added).length
  const copies = Object.keys(ids.copies).length
  return [
    `Writes ${plural(operations, 'operation')} beside the baseline in one write:`,
    [
      added ? `${plural(added, 'added element')} as ${added === 1 ? 'a draft' : 'drafts'}` : '',
      copies ? `${plural(copies, '"(target)" copy', '"(target)" copies')} of what it changes` : '',
      'a Baseline and a Target plateau with a gap between them',
    ].filter(Boolean).join(', ') + '.',
    'The elements it changes stay as they are until it is moved into the baseline.',
  ].join(' ')
}

/**
 * The generated operations as lines a reader follows: an element named by what the operations create it as,
 * or by its part in the target state, rather than by its id. The server answers every element by the id it
 * is given, so nothing here reads how operations name what they create before it has one.
 */
export const targetOperationLines = (
  operations: readonly Readonly<Record<string, unknown>>[], ids: TargetStateIds | null,
): string[] => {
  const names = new Map<string, string>()
  for (const operation of operations) {
    const fields = (operation.fields ?? {}) as Readonly<Record<string, unknown>>
    if (operation.op !== 'create_entity' || typeof fields.name !== 'string') continue
    if (typeof operation.artifact_id === 'string') names.set(stableEntityId(operation.artifact_id), fields.name)
  }
  // What the operations do not create — a move takes these away — is named by its part in the target state.
  const parts: [string, string][] = ids
    ? [
      [ids.baseline, 'the Baseline plateau'], [ids.target, 'the Target plateau'], [ids.gap, 'the gap'],
      ...Object.values(ids.copies).map((copy): [string, string] => [copy, 'a "(target)" copy']),
    ]
    : []
  for (const [id, part] of parts) if (!names.has(stableEntityId(id))) names.set(stableEntityId(id), part)
  const named = (line: string): string => line.replace(ELEMENT, (id) => names.get(stableEntityId(id)) ?? id)
  return operations.map((operation) => named(operationLabel(operation)))
}

/** An element id, as an operation line spells it. */
const ELEMENT = /[A-Z]{2,6}@[\w.-]+/g

/** What moving into the baseline writes, in one sentence. */
export const moveSentence = (operations: number): string =>
  `Writes ${plural(operations, 'operation')} in one write: the candidate's changes onto the originals, then `
  + 'the "(target)" copies, the plateaus and the gap are removed.'

/** What withdrawing a target state writes, in one sentence. */
export const withdrawSentence = (operations: number): string =>
  `Writes ${plural(operations, 'operation')} in one write: the "(target)" copies, the elements it added, the `
  + 'plateaus and the gap are removed with their relations. The baseline stays as it is, and the candidate '
  + 'becomes a draft again.'
