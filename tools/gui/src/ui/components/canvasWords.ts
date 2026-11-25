/** What the shared canvas editor calls deleting an element: the diagram page's words, or a candidate's. */
export interface CanvasWords {
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
}

export const DIAGRAM_WORDS: CanvasWords = {
  deleteEntry: 'Delete from model…',
  deleteHint: 'everywhere, with its relations; asks first',
  deleteQuestion: (name) => `Delete ${name} from the model at Save?`,
  deleteConfirm: 'Delete from model',
  removeEntry: 'Remove from diagram',
  removeHint: 'it stays in the model',
  removeKey: 'Del',
}

/** A candidate's words (06·5): removing records a remove-entity operation; the model keeps it until Apply. */
export const CANDIDATE_WORDS: CanvasWords = {
  deleteEntry: 'Remove from the candidate…',
  deleteHint: 'records a remove-entity operation; asks first',
  deleteQuestion: (name) =>
    `Remove ${name} from this candidate? It records a remove-entity operation; the model keeps it until the candidate is applied.`,
  deleteConfirm: 'Remove from the candidate',
  removeEntry: 'Remove from view',
  removeHint: 'records nothing; the candidate keeps it',
}
