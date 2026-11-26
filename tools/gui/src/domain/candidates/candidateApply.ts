/**
 * Applying a candidate to the model directly, as its page previews it: the dry run's answer read as
 * what would be written, what is skipped because the model already says it, and the refusal. Nothing
 * here judges an operation: the standing and the refusal are the server's, in its own words.
 */
import type { CandidateApplication, OperationStanding } from '../schemas/candidates'

export interface ApplyPreview {
  /** The operations the apply writes, in the order the server applies them. */
  readonly writes: readonly OperationStanding[]
  /** The operations the model already holds, which the apply skips. */
  readonly skipped: readonly OperationStanding[]
  /** Why the candidate cannot be applied; null when it can. */
  readonly refusal: string | null
}

export const applyPreview = (answer: CandidateApplication): ApplyPreview => ({
  writes: answer.standing.filter((one) => one.standing !== 'already-there'),
  skipped: answer.standing.filter((one) => one.standing === 'already-there'),
  refusal: answer.refusal ?? null,
})

/** Whether confirming would write: nothing refuses it and there is something to write or skip. */
export const canApply = (preview: ApplyPreview): boolean =>
  preview.refusal === null && preview.writes.length + preview.skipped.length > 0

const operations = (count: number): string => `${count} operation${count === 1 ? '' : 's'}`

/** The preview's sentence: how many operations are written in the one write, and how many skipped. */
export const previewSentence = ({ writes, skipped }: ApplyPreview): string => [
  writes.length ? `Writes ${operations(writes.length)} to the model in one write.` : 'Writes nothing to the model.',
  skipped.length
    ? `Skips ${operations(skipped.length)} the model already ${skipped.length === 1 ? 'holds' : 'hold'}.`
    : '',
].filter(Boolean).join(' ')

const text = (value: unknown): string => (typeof value === 'string' ? value : '')

const connection = (operation: Readonly<Record<string, unknown>>): string =>
  `${text(operation.source_entity)} → ${text(operation.target_entity)} (${text(operation.connection_type)})`

const field = (operation: Readonly<Record<string, unknown>>): string =>
  [text(operation.field), text(operation.key)].filter(Boolean).join('.')

/** One operation as a line of the preview: what it does, and to what. */
export const operationLabel = (operation: Readonly<Record<string, unknown>>): string => {
  const fields = (operation.fields ?? {}) as Readonly<Record<string, unknown>>
  switch (operation.op) {
    case 'create_entity': return `Create ${text(fields.name) || text(operation.artifact_id)}`
    case 'edit_entity': return `Set ${field(operation)} of ${text(operation.artifact_id)}`
    case 'remove_entity': return `Remove ${text(operation.artifact_id)}`
    case 'add_connection': return `Connect ${connection(operation)}`
    case 'edit_connection': return `Set ${field(operation)} of ${connection(operation)}`
    case 'remove_connection': return `Disconnect ${connection(operation)}`
    default: return text(operation.op)
  }
}

/** What an edit changes its field (or key) from and to: the value its base was written over, and its own. */
export interface EditedValues {
  readonly before: unknown
  readonly after: unknown
}

/**
 * The values an edit operation changes between, for `FieldChangeView`; null for any other operation, and for an
 * edit whose base names a revision rather than the value it was written over.
 */
export const editedValues = (operation: Readonly<Record<string, unknown>>): EditedValues | null => {
  const base = operation.base
  const edits = operation.op === 'edit_entity' || operation.op === 'edit_connection'
  return edits && typeof base === 'object' && base !== null && 'value' in base
    ? { before: base.value, after: operation.value }
    : null
}
