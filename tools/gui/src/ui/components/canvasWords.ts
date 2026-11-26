import { CANDIDATE_OPERATIONS, type CommandOperations, DIAGRAM_OPERATIONS } from '../../domain/canvasCommands'

/**
 * What the shared canvas editor calls deleting an element: the diagram page's words, or a candidate's —
 * and what each of its commands is an operation of on that page.
 */
export interface CanvasWords {
  /** The named operation each command is here (`canvasCommands`), which the permission answer is keyed by. */
  readonly operations: CommandOperations
  readonly deleteEntry: string
  /** The delete entry's one-line hint in the element's menu. */
  readonly deleteHint: string
  readonly deleteQuestion: (name: string) => string
  readonly deleteConfirm: string
  /** Taking an element off this view only, recording nothing; offered where deleting is not removing. */
  readonly removeEntry?: string
  /** What removing leaves standing, under the remove entry. */
  readonly removeHint?: string
  /** The key on the canvas that removes the selection too, shown beside the entry. */
  readonly removeKey?: string
  /** What nesting *part* in *whole* by a containment relationship has done, said once it is chosen (03·10). */
  readonly nested: (part: string, whole: string) => string
  /** Putting a selection in a new box; offered where the page edits the diagram's boxes, as is a box's menu. */
  readonly newBoxEntry?: string
}

export const DIAGRAM_WORDS: CanvasWords = {
  operations: DIAGRAM_OPERATIONS,
  deleteEntry: 'Delete from model…',
  deleteHint: 'everywhere, with its relations; asks first',
  deleteQuestion: (name) => `Delete ${name} from the model at Save?`,
  deleteConfirm: 'Delete from model',
  removeEntry: 'Remove from diagram',
  removeHint: 'it stays in the model',
  removeKey: 'Del',
  nested: (part, whole) => `${part} becomes part of ${whole}: a model change, written to the model when you Save.`,
  newBoxEntry: 'Put in a new box…',
}

/** A candidate's words (06·5): removing records a remove-entity operation; the model keeps it until Apply. */
export const CANDIDATE_WORDS: CanvasWords = {
  operations: CANDIDATE_OPERATIONS,
  deleteEntry: 'Remove from the candidate…',
  deleteHint: 'records a remove-entity operation; asks first',
  deleteQuestion: (name) =>
    `Remove ${name} from this candidate? It records a remove-entity operation; the model keeps it until Apply.`,
  deleteConfirm: 'Remove from the candidate',
  removeEntry: 'Remove from view',
  removeHint: 'records nothing; the candidate keeps it',
  nested: (part, whole) => `${part} becomes part of ${whole}: recorded in the candidate as a new relationship.`,
}
