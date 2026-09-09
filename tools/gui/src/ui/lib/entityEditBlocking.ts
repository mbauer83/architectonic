/**
 * What the entity-detail edit form says about itself: why a save is disabled, and what saving
 * will do. Shared by the header's action trio and the card's — both drive the same edit
 * transaction, so a divergent explanation there would be a bug in itself.
 *
 * Quarantine outranks the missing-required-property reason: that one the operator can fix
 * in the form, whereas a quarantined (type, specialization) pair cannot be saved at all
 * until its schema declarations are reconciled outside it.
 */

export const EDIT_QUARANTINE_TITLE = 'Resolve the schema conflict shown in the form before saving'
export const EDIT_REQUIRED_TITLE = 'Fill in all required properties first'

export const editBlockedReason = (quarantined: boolean, requiredMissing: boolean): string | undefined => {
  if (quarantined) return EDIT_QUARANTINE_TITLE
  return requiredMissing ? EDIT_REQUIRED_TITLE : undefined
}


/**
 * What saving this edit actually does, which is not the same question on every artifact.
 *
 * An engagement repository cannot write enterprise content, so an edit of a promoted artifact is
 * recorded as a local change, which goes upstream when it is submitted. That is the ordinary
 * case for anything marked
 * Enterprise, and the reason the edit affordance exists there at all: it was hidden, so the only
 * interface most people use offered no way to reach the feature — and no explanation either.
 *
 * Admin mode is the third case and the dangerous one: there the write does land upstream, which is
 * what the warning sign beside it has always been for.
 */
export type EditOutcome = 'writes-here' | 'records-a-change' | 'writes-upstream'

export const editOutcome = (isGlobalEntity: boolean, adminMode: boolean): EditOutcome => {
  if (!isGlobalEntity) return 'writes-here'
  return adminMode ? 'writes-upstream' : 'records-a-change'
}

/** What the Edit control promises, for the hover text that sets an expectation before the click. */
export const editOutcomeTitle = (outcome: EditOutcome): string | undefined => {
  switch (outcome) {
    case 'writes-here':
      return undefined
    case 'records-a-change':
      return 'This artifact belongs to the enterprise repository. '
        + 'Your edit is recorded as a local change, and goes there when you submit it for review.'
    case 'writes-upstream':
      return 'Edit global entity (admin mode)'
  }
}

/** What to say after a save, which is not "saved" when nothing was saved here. */
export const savedMessage = (outcome: EditOutcome): string =>
  outcome === 'records-a-change' ? 'Change recorded' : 'Entity saved'

/**
 * Whether the id a save answered with is the artifact to go to.
 *
 * A rename answers with the artifact's new id and the view must follow it. Recording a change
 * answers with the *change's* id — an internal artifact nobody should be shown, and following it
 * navigated the reader straight into one.
 */
export const savedIdIsTheArtifact = (outcome: EditOutcome): boolean =>
  outcome !== 'records-a-change'
