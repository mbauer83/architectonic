/** What the shared canvas editor calls deleting an element: the diagram page's words, or a candidate's. */
export interface CanvasWords {
  readonly deleteEntry: string
  readonly deleteQuestion: (name: string) => string
  readonly deleteConfirm: string
  /** Taking an element off this view only, recording nothing; offered where deleting is not removing. */
  readonly removeEntry?: string
}

export const DIAGRAM_WORDS: CanvasWords = {
  deleteEntry: 'Delete from model…',
  deleteQuestion: (name) => `Delete ${name} from the model at Save?`,
  deleteConfirm: 'Confirm deletion',
}

/** A candidate's words (06·5): removing records a remove-entity operation; the model keeps it until Commit. */
export const CANDIDATE_WORDS: CanvasWords = {
  deleteEntry: 'Remove from the candidate…',
  deleteQuestion: (name) =>
    `Remove ${name} from this candidate? It records a remove-entity operation; the model keeps it until Commit.`,
  deleteConfirm: 'Remove from the candidate',
  removeEntry: 'Remove from view',
}
